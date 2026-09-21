"""RAG: chunking, embeddings, ingestion, semantic search."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Document, DocumentChunk


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    filename: str
    text: str
    page_number: int | None
    score: float
    metadata: dict[str, Any]


class EmbeddingService:
    """Local embeddings via sentence-transformers, with hash fallback for tests."""

    def __init__(self) -> None:
        self._model = None
        self.dimension = get_settings().embedding_dimension

    def _load(self) -> None:
        if self._model is not None:
            return
        settings = get_settings()
        if not settings.use_local_embeddings or settings.app_env == "test":
            self._model = "hash"
            return
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(settings.embedding_model)
            self.dimension = self._model.get_sentence_embedding_dimension()
        except Exception:
            self._model = "hash"

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._load()
        if self._model == "hash":
            return [self._hash_embed(t) for t in texts]
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]

    def _hash_embed(self, text: str) -> list[float]:
        """Deterministic pseudo-embedding for tests without heavy models."""
        dim = self.dimension
        vec = np.zeros(dim, dtype=np.float64)
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        for tok in tokens:
            h = hashlib.sha256(tok.encode()).digest()
            idx = int.from_bytes(h[:4], "big") % dim
            sign = 1.0 if h[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(
    text: str, chunk_size: int | None = None, overlap: int | None = None
) -> list[str]:
    settings = get_settings()
    chunk_size = chunk_size or settings.rag_chunk_size
    overlap = overlap if overlap is not None else settings.rag_chunk_overlap
    if chunk_size <= 0:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float64)
    vb = np.array(b, dtype=np.float64)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


class RAGService:
    def __init__(self, embedding_service: EmbeddingService | None = None):
        self.embeddings = embedding_service or EmbeddingService()

    async def ingest_pdf(
        self,
        db: AsyncSession,
        filename: str,
        file_bytes: bytes,
        metadata: dict[str, Any] | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> Document:
        from io import BytesIO

        from pypdf import PdfReader

        reader = PdfReader(BytesIO(file_bytes))
        pages: list[tuple[int, str]] = []
        for i, page in enumerate(reader.pages):
            raw = page.extract_text() or ""
            pages.append((i + 1, clean_text(raw)))

        full_text = "\n\n".join(t for _, t in pages if t)
        doc = Document(
            id=str(uuid.uuid4()),
            filename=filename,
            content_type="application/pdf",
            page_count=len(reader.pages),
            metadata_json=metadata or {},
        )
        db.add(doc)
        await db.flush()

        # Chunk per page to preserve page numbers
        all_chunks: list[tuple[int, str]] = []
        for page_num, page_text in pages:
            if not page_text:
                continue
            for c in chunk_text(page_text, chunk_size, chunk_overlap):
                all_chunks.append((page_num, c))

        if not all_chunks and full_text:
            for c in chunk_text(full_text, chunk_size, chunk_overlap):
                all_chunks.append((1, c))

        vectors = self.embeddings.embed([c for _, c in all_chunks]) if all_chunks else []
        for idx, ((page_num, text), vec) in enumerate(zip(all_chunks, vectors)):
            chunk = DocumentChunk(
                id=str(uuid.uuid4()),
                document_id=doc.id,
                chunk_index=idx,
                chunk_text=text,
                page_number=page_num,
                embedding=vec,
                metadata_json={"filename": filename},
            )
            db.add(chunk)

        doc.chunk_count = len(all_chunks)
        await db.flush()
        return doc

    async def ingest_text(
        self,
        db: AsyncSession,
        filename: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> Document:
        text = clean_text(text)
        doc = Document(
            id=str(uuid.uuid4()),
            filename=filename,
            content_type="text/plain",
            page_count=1,
            metadata_json=metadata or {},
        )
        db.add(doc)
        await db.flush()

        pieces = chunk_text(text, chunk_size, chunk_overlap)
        vectors = self.embeddings.embed(pieces)
        for idx, (piece, vec) in enumerate(zip(pieces, vectors)):
            db.add(
                DocumentChunk(
                    id=str(uuid.uuid4()),
                    document_id=doc.id,
                    chunk_index=idx,
                    chunk_text=piece,
                    page_number=1,
                    embedding=vec,
                    metadata_json={"filename": filename},
                )
            )
        doc.chunk_count = len(pieces)
        await db.flush()
        return doc

    async def search(
        self,
        db: AsyncSession,
        query: str,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
        document_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        settings = get_settings()
        top_k = top_k or settings.rag_top_k
        threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else settings.rag_similarity_threshold
        )
        query_vec = self.embeddings.embed_query(query)

        stmt = select(DocumentChunk, Document).join(
            Document, DocumentChunk.document_id == Document.id
        )
        if document_ids:
            stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))
        result = await db.execute(stmt)
        rows = result.all()

        scored: list[RetrievedChunk] = []
        for chunk, doc in rows:
            if not chunk.embedding:
                continue
            score = cosine_similarity(query_vec, chunk.embedding)
            if score >= threshold:
                scored.append(
                    RetrievedChunk(
                        chunk_id=chunk.id,
                        document_id=doc.id,
                        filename=doc.filename,
                        text=chunk.chunk_text,
                        page_number=chunk.page_number,
                        score=score,
                        metadata=chunk.metadata_json or {},
                    )
                )
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]


_rag: RAGService | None = None


def get_rag_service() -> RAGService:
    global _rag
    if _rag is None:
        _rag = RAGService()
    return _rag
