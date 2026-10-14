"""FastAPI application factory (M1): health endpoint + run-ID logging."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from threadline import __version__
from threadline.config import Settings, get_settings
from threadline.persistence.database import init_storage, create_session_factory
from threadline.retrieval.vector import create_vector_adapter, create_embedding_provider
from threadline.integrations.goose import create_goose_adapter
from threadline.memory.manager import MemoryManager
from threadline.memory.checkpoint import CheckpointManager
from threadline.orchestration.graph import build_investigation_graph
from threadline.audit import AuditManager
from threadline.api.routes_documents import router as documents_router
from threadline.api.routes_investigations import router as investigations_router
from threadline.api.routes_retrieval import router as retrieval_router
from threadline.redact import redact_secrets

RUN_ID_HEADER = "X-Threadline-Run-Id"

UI_DIR = Path(__file__).resolve().parent / "ui"
# Untrusted document and tool text is rendered by the UI, so scripts and styles may only
# come from this origin. The page itself has no inline script or style.
UI_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)

logger = logging.getLogger("threadline")


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app. Raises on invalid config (fail fast, redacted)."""
    resolved = settings or get_settings()
    _configure_logging(resolved.log_level)

    engine, session_factory = create_session_factory(resolved)

    # Optional vector backend and memory/checkpoint/integration graph state.
    vector_adapter = create_vector_adapter(resolved) if resolved.vector_enabled else None
    embedding_provider = create_embedding_provider(resolved) if vector_adapter is not None else None
    checkpoint_manager = CheckpointManager(resolved)
    memory_manager = MemoryManager(
        settings=resolved,
        session_factory=(engine, session_factory),
        vector_adapter=vector_adapter,
        embedding_provider=embedding_provider,
        checkpoint_manager=checkpoint_manager,
    )
    goose_adapter = create_goose_adapter(resolved)
    audit_manager = AuditManager((engine, session_factory))
    investigation_graph = build_investigation_graph(
        settings=resolved,
        checkpoint_manager=checkpoint_manager,
        memory_manager=memory_manager,
        goose_adapter=goose_adapter,
        audit_manager=audit_manager,
    )

    @asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            init_storage(resolved)
        except RuntimeError as exc:
            logger.error("storage init failed: %s", redact_secrets(str(exc)))
            raise
        yield

    app = FastAPI(title="Threadline", version=__version__, lifespan=_lifespan)
    app.state.settings = resolved
    app.state.engine = engine
    app.state.vector_adapter = vector_adapter
    app.state.embedding_provider = embedding_provider
    app.state.checkpoint_manager = checkpoint_manager
    app.state.memory_manager = memory_manager
    app.state.audit_manager = audit_manager
    app.state.investigation_graph = investigation_graph
    app.state.session_factory = session_factory
    app.include_router(investigations_router)
    app.include_router(documents_router)
    app.include_router(retrieval_router)

    app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")
    index_html = (UI_DIR / "index.html").read_text(encoding="utf-8")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def ui_index() -> HTMLResponse:
        return HTMLResponse(index_html, headers={"Content-Security-Policy": UI_CONTENT_SECURITY_POLICY})

    @app.middleware("http")
    async def _run_id_middleware(request: Request, call_next):
        run_id = uuid.uuid4().hex[:16]
        request.state.run_id = run_id
        logger.info("request started run_id=%s method=%s path=%s", run_id, request.method, request.url.path)
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request failed run_id=%s", run_id)
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal error", "run_id": run_id},
                headers={RUN_ID_HEADER: run_id},
            )
        response.headers[RUN_ID_HEADER] = run_id
        logger.info("request completed run_id=%s status=%s", run_id, response.status_code)
        return response

    @app.get("/health")
    def health(request: Request) -> dict:
        cfg: Settings = request.app.state.settings
        return {
            "status": "ok",
            "version": __version__,
            "env": cfg.threadline_env,
            "run_id": getattr(request.state, "run_id", None),
        }

    return app


# Default instance for `uvicorn threadline.main:app`.
try:
    app = create_app()
except Exception as exc:  # import-time failure must stay secret-free and actionable
    logger.error("Failed to create default app: %s", redact_secrets(str(exc)))
    raise
