"""AgentForge application settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AgentForge"
    app_env: Literal["development", "staging", "production", "test"] = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"
    secret_key: str = Field(default="change-me-in-production-use-openssl-rand")
    access_token_expire_minutes: int = 60 * 24

    # Database
    database_url: str = (
        "postgresql+asyncpg://agentforge:agentforge@localhost:5432/agentforge"
    )
    database_url_sync: str = (
        "postgresql://agentforge:agentforge@localhost:5432/agentforge"
    )
    # Use SQLite for local tests when Postgres is unavailable
    use_sqlite: bool = False
    sqlite_url: str = "sqlite+aiosqlite:///./agentforge.db"

    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    # Optional regex for generated hostnames, e.g. a Vercel project's production domain
    cors_origin_regex: str = ""

    # LLM providers
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    openrouter_api_key: str = ""
    # A pinned free chat model; "openrouter/free" can route to non-chat models
    # (e.g. a safety classifier that replies "User Safety: safe")
    openrouter_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    llm_mock_mode: bool = True  # mock providers when keys absent

    # Embeddings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    use_local_embeddings: bool = True

    # RAG defaults
    rag_chunk_size: int = 800
    rag_chunk_overlap: int = 120
    rag_top_k: int = 5
    rag_similarity_threshold: float = 0.35

    # Agent runtime
    max_agent_iterations: int = 5
    max_prompt_length: int = 16_000
    log_full_prompts: bool = False

    # Uploads
    upload_dir: str = "./uploads"

    # Create a demo agent and knowledge doc on startup when the DB is empty
    seed_demo: bool = False

    # Auth (simple API key for admin ops in demo)
    admin_api_key: str = "agentforge-admin-dev-key"
    auth_enabled: bool = False  # disabled for local demo; enable in prod

    # Rate limiting
    rate_limit_per_minute: int = 120

    # Observability
    metrics_enabled: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def effective_database_url(self) -> str:
        if self.use_sqlite or self.app_env == "test":
            return self.sqlite_url
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
