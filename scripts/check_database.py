from sqlalchemy import inspect, text

from app.db import DatabaseNotConfigured, get_engine


def main() -> None:
    try:
        engine = get_engine()
        with engine.connect() as connection:
            identity = connection.execute(
                text("SELECT current_database(), current_user, current_setting('server_version')")
            ).one()
            tables = inspect(connection).get_table_names(schema="public")
            revision = None
            if "alembic_version" in tables:
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one_or_none()
    except DatabaseNotConfigured as exc:
        raise SystemExit(str(exc)) from exc
    except Exception as exc:
        raise SystemExit(f"Falha ao conectar ao PostgreSQL: {type(exc).__name__}") from exc

    print(f"Banco: {identity[0]}")
    print(f"Usuário: {identity[1]}")
    print(f"PostgreSQL: {identity[2]}")
    print(f"Migração atual: {revision or 'não aplicada'}")
    print(f"Tabelas públicas: {len(tables)}")


if __name__ == "__main__":
    main()

