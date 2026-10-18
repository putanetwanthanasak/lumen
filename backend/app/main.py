import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from app.config import Settings, get_settings
from app.db import describe_db_error
from app.debts.router import router as debts_router
from app.disputes.router import router as disputes_router
from app.webhooks.router import router as webhooks_router

logger = logging.getLogger(__name__)


async def _db_error(request: Request, exc: Exception) -> JSONResponse:
    # S12: the default 500 handler logs the full error text, which quotes the failing
    # row. Log only what describe_db_error allows; the client gets nothing internal.
    logger.error(
        "database error on %s %s: %s", request.method, request.url.path, describe_db_error(exc)
    )
    return JSONResponse(status_code=500, content={"detail": "internal error"})


def create_app(settings: Settings) -> FastAPI:
    # S12: no public map of the API unless DEBUG is on.
    docs = settings.debug
    app = FastAPI(
        title="Lumen",
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.add_exception_handler(DBAPIError, _db_error)
    app.include_router(webhooks_router)
    app.include_router(debts_router)
    app.include_router(disputes_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe. Does not touch the database."""
        return {"status": "ok"}

    return app


app = create_app(get_settings())
