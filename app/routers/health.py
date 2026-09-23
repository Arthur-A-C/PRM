from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.db import DatabaseNotConfigured, get_engine


router = APIRouter(prefix="/api/v1/health", tags=["saúde"])


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/ready",
    response_model=None,
    responses={503: {"description": "Banco indisponível"}},
)
def ready() -> dict[str, str] | JSONResponse:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except DatabaseNotConfigured:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "not_configured"},
        )
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "unavailable"},
        )
    return {"status": "ok", "database": "available"}
