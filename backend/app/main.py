"""AgentForge FastAPI application."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import get_settings
from app.core.exceptions import AgentForgeError
from app.core.logging import get_logger, setup_logging
from app.core.security import rate_limit_dependency
from app.db.session import init_db
from app.mcp.client import ensure_default_mcp_connected

setup_logging()
logger = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    await init_db()
    await ensure_default_mcp_connected()
    logger.info("agentforge_started", env=settings.app_env)
    yield
    logger.info("agentforge_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description="Production-oriented AI agent platform",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AgentForgeError)
    async def agentforge_error_handler(request: Request, exc: AgentForgeError):
        status = 404 if exc.code == "not_found" else 400
        if exc.code == "guardrail_failure":
            status = 422
        return JSONResponse(
            status_code=status,
            content={"code": exc.code, "message": exc.message},
        )

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        if request.url.path.endswith("/metrics") or request.url.path.endswith("/health"):
            return await call_next(request)
        try:
            await rate_limit_dependency(request)
        except Exception as exc:
            from fastapi import HTTPException

            if isinstance(exc, HTTPException):
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
            raise
        return await call_next(request)

    app.include_router(router, prefix=settings.api_prefix)
    # Also expose health at root for k8s probes
    @app.get("/health")
    async def root_health():
        return {"status": "ok"}

    @app.get("/metrics")
    async def root_metrics():
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
        from starlette.responses import Response

        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
