import logging
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryFile

from alembic.runtime.migration import MigrationContext
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles

from app.core.config import Settings
from app.core.logging import configure_logging
from app.core.middleware import RequestPolicy
from app.database.session import build_engine, schema_head, session_factory
from app.ddi import (
    config_data,  # noqa: F401 -- registers ConfigData route
    deployment,  # noqa: F401 -- registers delivery routes
)
from app.ddi.controller import router
from app.management.auth import router as auth_router
from app.management.resources import router as management_router
from app.services.artifact_storage import LocalArtifactStorage

log = logging.getLogger("ota")


def check_dependencies(engine, storage, head):
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        current = MigrationContext.configure(connection).get_current_revision()
        if current != head:
            raise RuntimeError("Database schema is not current; run alembic upgrade head")
    with TemporaryFile(dir=storage) as probe:
        probe.write(b"ota-readiness-probe")
        probe.flush()


def create_app(settings=None):
    settings = settings or Settings()
    configure_logging(settings.log_level)
    engine = build_engine(settings.database_url)
    storage = Path(settings.artifact_storage_path)
    head = schema_head()

    @asynccontextmanager
    async def lifespan(app):
        try:
            storage.mkdir(parents=True, exist_ok=True)
            check_dependencies(engine, storage, head)
            log.info("application.startup", extra={"fields": {"stage": "management"}})
            yield
        finally:
            engine.dispose()

    app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessions = session_factory(engine)
    app.state.storage = LocalArtifactStorage(storage)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(RequestPolicy, max_body_bytes=settings.max_ddi_body_bytes)
    app.include_router(router)
    app.include_router(auth_router)
    app.include_router(management_router)

    @app.exception_handler(IntegrityError)
    async def conflict(request: Request, exc):
        return JSONResponse(
            {"detail": "Resource already exists or conflicts with current state"}, status_code=409
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc):
        # Never echo submitted credentials or raw input in validation errors.
        return JSONResponse({"detail": "Invalid request body or parameters"}, status_code=400)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc):
        log.error(
            "database.unavailable", extra={"fields": {"request_id": request.state.request_id}}
        )
        return JSONResponse({"detail": "Database temporarily unavailable"}, status_code=503)

    @app.get("/health", tags=["Operations"])
    def health():
        return {"status": "ok", "stage": "management"}

    @app.get("/ready", tags=["Operations"])
    def ready():
        try:
            check_dependencies(engine, storage, head)
        except (SQLAlchemyError, OSError, RuntimeError):
            return JSONResponse({"status": "not_ready"}, status_code=503)
        return {"status": "ready"}

    frontend = Path(settings.frontend_path).resolve()
    if (frontend / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="dashboard-assets")

    @app.get("/", include_in_schema=False)
    def dashboard():
        if not (frontend / "index.html").is_file():
            return JSONResponse(
                {
                    "detail": "Dashboard build missing. Run npm ci && npm run build "
                    "in frontend/. APIs are available at /docs."
                },
                status_code=503,
            )
        return FileResponse(frontend / "index.html")

    return app
