"""Evaluation framework for agent quality assessment."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvalExample:
    question: str
    expected_answer: str
    expected_source: str | None = None


@dataclass
class EvalCaseResult:
    question: str
    expected_answer: str
    actual_answer: str
    metrics: dict[str, Any] = field(default_factory=dict)


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def answer_correctness(expected: str, actual: str) -> float:
    """Token-overlap F1-style heuristic (not LLM-as-judge)."""
    exp = _tokenize(expected)
    act = _tokenize(actual)
    if not exp or not act:
        return 0.0
    overlap = exp & act
    precision = len(overlap) / len(act)
    recall = len(overlap) / len(exp)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def faithfulness(answer: str, context_chunks: list[str]) -> float:
    """Fraction of answer tokens that appear in retrieved context."""
    if not context_chunks:
        return 1.0  # no RAG — N/A treated as pass
    ctx = _tokenize(" ".join(context_chunks))
    ans = _tokenize(answer)
    if not ans:
        return 0.0
    return len(ans & ctx) / len(ans)


def retrieval_relevance(expected_source: str | None, citations: list[dict]) -> float:
    if not expected_source:
        return 1.0
    if not citations:
        return 0.0
    names = " ".join(c.get("filename", "") for c in citations).lower()
    return 1.0 if expected_source.lower() in names else 0.0


def llm_as_judge_correctness(expected: str, actual: str) -> dict[str, Any]:
    """Lightweight heuristic labeled as LLM-as-judge placeholder.

    Clearly labeled — not claimed as objective ground truth.
    Uses overlap as a stand-in when no judge model is configured.
    """
    score = answer_correctness(expected, actual)
    return {
        "method": "llm_as_judge_heuristic",
        "label": "LLM-as-judge (heuristic stand-in; not objective)",
        "score": score,
        "rationale": "Score derived from token overlap when no judge model is configured.",
    }


class EvaluationRunner:
    async def run_case(
        self,
        example: EvalExample,
        actual_answer: str,
        *,
        citations: list[dict] | None = None,
        context_chunks: list[str] | None = None,
        tool_success: bool | None = None,
        latency_ms: float = 0.0,
        estimated_cost_usd: float = 0.0,
    ) -> EvalCaseResult:
        citations = citations or []
        context_chunks = context_chunks or [c.get("snippet", "") for c in citations]
        metrics = {
            "answer_correctness": answer_correctness(
                example.expected_answer, actual_answer
            ),
            "faithfulness": faithfulness(actual_answer, context_chunks),
            "retrieval_relevance": retrieval_relevance(
                example.expected_source, citations
            ),
            "tool_success_rate": 1.0 if tool_success is None else (1.0 if tool_success else 0.0),
            "latency_ms": latency_ms,
            "estimated_cost_usd": estimated_cost_usd,
            "llm_judge": llm_as_judge_correctness(
                example.expected_answer, actual_answer
            ),
        }
        return EvalCaseResult(
            question=example.question,
            expected_answer=example.expected_answer,
            actual_answer=actual_answer,
            metrics=metrics,
        )

    def aggregate(self, cases: list[EvalCaseResult]) -> dict[str, Any]:
        if not cases:
            return {}
        keys = [
            "answer_correctness",
            "faithfulness",
            "retrieval_relevance",
            "tool_success_rate",
            "latency_ms",
            "estimated_cost_usd",
        ]
        agg: dict[str, Any] = {"n": len(cases)}
        for k in keys:
            vals = [c.metrics[k] for c in cases]
            agg[k] = {
                "mean": sum(vals) / len(vals),
                "min": min(vals),
                "max": max(vals),
            }
        agg["note"] = (
            "LLM-as-judge scores are labeled heuristics and are not objective correctness."
        )
        return agg
