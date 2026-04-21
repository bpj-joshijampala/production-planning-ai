import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.paths import ensure_runtime_directories


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    ensure_runtime_directories(settings)

    logger = logging.getLogger(__name__)
    logger.info(
        "Starting %s version=%s env=%s database=%s uploads=%s exports=%s",
        settings.app_name,
        settings.app_version,
        settings.app_env,
        settings.database_url,
        settings.upload_dir,
        settings.export_dir,
    )

    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api/v1")
    return app


app = create_app()
