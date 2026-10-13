"""Somente leitura: inventário SQL sem imprimir URL/credenciais."""

import json

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings


def main():
    url = make_url(get_settings().database_url)
    for database in [url.database, "prm_pipeline_staging"]:
        engine = create_engine(url.set(database=database), connect_args={"connect_timeout": 5})
        try:
            with engine.connect() as conn:
                conn.execute(text("SET TRANSACTION READ ONLY"))
                rows = conn.execute(text("SELECT c.code,count(o.id) FROM companies c LEFT JOIN offers o ON o.company_id=c.id GROUP BY c.code ORDER BY c.code")).all()
                batches = conn.execute(text("SELECT count(*) FROM catalog_imports")).scalar_one()
                revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                print(json.dumps({"database": database, "company_counts": dict(rows), "batches": batches, "revision": revision}))
        except SQLAlchemyError as exc:
            # Nunca incluir exceção completa: pode conter string de conexão/payload.
            print(json.dumps({"database": database, "available": False, "error_type": type(exc).__name__}))
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
