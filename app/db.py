from collections.abc import Generator
from functools import lru_cache

from fastapi import HTTPException, status
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.config import get_settings


class DatabaseNotConfigured(RuntimeError):
    pass


@lru_cache
def get_engine() -> Engine:
    database_url = get_settings().database_url
    if not database_url:
        raise DatabaseNotConfigured(
            "Banco não configurado. Defina PRM_DATABASE_URL no arquivo .env."
        )
    if not database_url.startswith(("postgresql+psycopg://", "postgresql://")):
        raise DatabaseNotConfigured("PRM_DATABASE_URL deve apontar para PostgreSQL.")
    return create_engine(database_url, pool_pre_ping=True, pool_recycle=1800)


def get_db_session() -> Generator[Session, None, None]:
    try:
        engine = get_engine()
    except DatabaseNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    with Session(engine) as session:
        yield session

