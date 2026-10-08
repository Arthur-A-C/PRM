"""Read-only verification of the isolated PostgreSQL staging database."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy import create_engine

from app.config import get_settings
from app.services.dimensional_dashboard import load_dimensional_database_status


def main() -> None:
    url = make_url(get_settings().database_url)
    if url.database != "prm_mvp":
        raise SystemExit("Expected the configured production database to be prm_mvp.")
    staging_url = url.set(database="prm_pipeline_staging")
    with create_engine(staging_url, pool_pre_ping=True).connect() as connection:
        identity = connection.execute(
            text("SELECT current_database(), current_user, current_setting('server_version')")
        ).one()
        tables = inspect(connection).get_table_names()
        print(f"database={identity[0]} user={identity[1]} postgres={identity[2]}")
        print(f"tables={len(tables)} names={','.join(sorted(tables))}")
        if "alembic_version" in tables:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
            print(f"revision={revision}")
        if "offers" in tables:
            print(f"offers={connection.execute(text('SELECT count(*) FROM offers')).scalar_one()}")
            for table, join in (
                ("offers", "company_id"),
                ("catalog_imports", "company_id"),
            ):
                count = connection.execute(text(
                    f"SELECT count(*) FROM {table} t JOIN companies c ON c.id=t.{join} "
                    "WHERE c.code='dimensional'"
                )).scalar_one()
                print(f"dimensional_{table}={count}")
            batch = connection.execute(text(
                "SELECT i.id, i.file_sha256, i.status, i.total_rows, i.inserted_count, "
                "i.warning_count, i.currency FROM catalog_imports i "
                "JOIN companies c ON c.id=i.company_id WHERE c.code='dimensional'"
            )).first()
            if batch:
                print(f"dimensional_batch={batch}")
                for table, column in (
                    ("import_rows", "catalog_import_id"),
                    ("offer_observations", "catalog_import_id"),
                ):
                    count = connection.execute(
                        text(f"SELECT count(*) FROM {table} WHERE {column}=:batch_id"),
                        {"batch_id": batch.id},
                    ).scalar_one()
                    print(f"dimensional_{table}={count}")
                prices = connection.execute(text(
                    "SELECT p.modality, p.state, count(*) FROM offer_prices p "
                    "JOIN offer_observations o ON o.id=p.observation_id "
                    "WHERE o.catalog_import_id=:batch_id GROUP BY p.modality,p.state "
                    "ORDER BY p.modality,p.state"
                ), {"batch_id": batch.id}).all()
                print(f"dimensional_prices={prices}")
                distinct_skus = connection.execute(text(
                    "SELECT count(DISTINCT o.external_code) FROM offers o "
                    "JOIN companies c ON c.id=o.company_id WHERE c.code='dimensional'"
                )).scalar_one()
                variants = connection.execute(text(
                    "SELECT raw_row->>'product_id' AS product_id, count(*) "
                    "FROM import_rows WHERE catalog_import_id=:batch_id "
                    "AND raw_row->>'product_id' IN ('1053625','197090','238948') "
                    "GROUP BY raw_row->>'product_id' ORDER BY product_id"
                ), {"batch_id": batch.id}).all()
                print(f"dimensional_distinct_skus={distinct_skus} variant_groups={variants}")
                if (
                    distinct_skus != 77_965
                    or batch.file_sha256 != "8ad7e0e63e265aa6ebfd34b06a530dc000177c11602c2a6920e80add3e211528"
                    or dict(variants) != {"1053625": 7, "197090": 2, "238948": 2}
                ):
                    raise SystemExit("Dimensional staging reconciliation failed.")
                organization_id = connection.execute(text(
                    "SELECT organization_id FROM companies WHERE code='dimensional'"
                )).scalar_one()
                print(f"dashboard_status={load_dimensional_database_status(organization_id)}")


if __name__ == "__main__":
    main()
