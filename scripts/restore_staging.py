"""Clone a verified production backup into an empty, exact-name staging DB."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url

from app.config import get_settings
from scripts.backup_database import find_pg_dump


STAGING_DATABASE = "prm_pipeline_staging"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    backup_root = Path("data/backups").resolve()
    backup = args.backup.resolve()
    if backup.parent != backup_root or not backup.is_file():
        raise SystemExit("Backup must be an existing file directly under data/backups.")
    digest = hashlib.sha256(backup.read_bytes()).hexdigest()
    if digest != args.sha256.lower():
        raise SystemExit("Backup SHA-256 mismatch; staging was not changed.")
    url = make_url(get_settings().database_url)
    if url.database != "prm_mvp":
        raise SystemExit("Configured database is not prm_mvp; staging was not changed.")
    staging_url = url.set(database=STAGING_DATABASE)
    engine = create_engine(staging_url, pool_pre_ping=True)
    with engine.connect() as connection:
        if connection.engine.url.database != STAGING_DATABASE or inspect(connection).get_table_names():
            raise SystemExit("Staging is not empty; refusing to overwrite existing data.")
    engine.dispose()
    restore = find_pg_dump().with_name("pg_restore.exe")
    environment = os.environ.copy()
    if url.password:
        environment["PGPASSWORD"] = url.password
    command = [
        str(restore), "--host", str(url.host or "127.0.0.1"),
        "--port", str(url.port or 5432), "--username", str(url.username or ""),
        "--dbname", STAGING_DATABASE, "--no-owner", "--no-privileges",
        "--exit-on-error", "--single-transaction", str(backup),
    ]
    subprocess.run(command, env=environment, check=True)
    print(f"Restored verified backup into {STAGING_DATABASE}: {backup.name} ({digest})")


if __name__ == "__main__":
    main()
