"""Bread's FastAPI application.

Run it with::

    uvicorn app.main:app --reload --port 8000    # from backend/
    python -m app.cli serve                      # same thing, with the warnings

Bread is local-first. It binds to 127.0.0.1, keeps every byte in ``data/``, and
makes no outbound request unless you ask it to download a model or collect a
dataset.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import REPO_ROOT, get_settings
from .db import get_engine, init_db
from .errors import RateLimitedError, register_exception_handlers
from .routers import (
    apikeys,
    chat,
    conversations,
    datasets,
    documents,
    knowledge,
    models,
    prompts,
    system,
    training,
)
from .routers import (
    settings as settings_router,
)
from .security import RateLimiter, caller_identity, ensure_lan_guard, require_api_key

logger = logging.getLogger("bread")

DESCRIPTION = """
Bread is a **local-first coding assistant**. It runs an open-weight model on your
own machine, indexes your own documents for retrieval, and fine-tunes adapters
with LoRA or QLoRA on your own GPU.

**What Bread is not.** It does not train a frontier model from scratch, and one
consumer GPU cannot do that. Bread starts from an existing open-weight coding
model and adapts it. See `docs/LIMITATIONS.md`.

**Privacy.** No telemetry, no analytics, no automatic uploads. The only outbound
requests are model or dataset downloads you explicitly confirm.
""".strip()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db(settings)

    with Session(get_engine(settings)) as session:
        settings_router.apply_persisted_overrides(session, settings)

    for warning in ensure_lan_guard(settings):
        logger.warning("%s", warning)

    logger.info(
        "Bread %s ready on http://%s:%s  (backend=%s, model=%s)",
        settings.app_version,
        settings.host,
        settings.port,
        settings.model_backend,
        settings.model_id,
    )
    yield

    from .services.inference import registry

    registry.stop_all()
    registry.unload()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Bread API",
        version=settings.app_version,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    limiter = RateLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds)
    app.state.rate_limiter = limiter

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        if request.url.path.startswith("/api") and request.url.path != "/api/health":
            try:
                limiter.check(caller_identity(request))
            except RateLimitedError as exc:
                return JSONResponse(status_code=exc.status_code, content=exc.to_payload())
        return await call_next(request)

    register_exception_handlers(app)

    # /api/health stays open so a process supervisor can probe it without a key.
    public = APIRouter()
    public.include_router(system.router)

    protected = APIRouter(dependencies=[Depends(require_api_key)])
    for router in (
        models.router,
        chat.router,
        conversations.router,
        knowledge.router,
        documents.router,
        datasets.router,
        training.router,
        settings_router.router,
        apikeys.router,
        prompts.router,
    ):
        protected.include_router(router)

    app.include_router(public, prefix="/api")
    app.include_router(protected, prefix="/api")

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built React app when ``frontend/dist`` exists.

    In development the frontend runs on Vite at :5173 and talks to this server
    over CORS, so a missing build directory is normal and not an error.
    """

    dist = REPO_ROOT / "frontend" / "dist"
    if not dist.exists():
        return

    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        # The catch-all must not swallow unknown API routes: a client asking for
        # /api/typo deserves a 404 with a JSON body, not the HTML shell.
        if full_path == "api" or full_path.startswith("api/"):
            raise StarletteHTTPException(status_code=404, detail="No such API route.")

        candidate = (dist / full_path).resolve()
        if dist.resolve() in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


app = create_app()
