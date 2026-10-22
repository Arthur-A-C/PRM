"""Synthetic persistence probe, allowed ONLY in the isolated Docker database."""
import argparse
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("write", "verify"))
    args = parser.parse_args()
    url = os.environ.get("PRM_DATABASE_URL", "")
    db = urlsplit(url)
    if db.hostname != "db" or db.path != "/prm_docker":
        raise SystemExit("Probe proibido fora de db/prm_docker.")
    folders = ("store_publish", "datasheet_batches", "integrations", "meetings", "products",
               "imports", "exports", "analysis", "backups", "tools")
    for folder in folders:
        path = Path("data") / folder / ".infra-persistence.txt"
        if args.mode == "write":
            path.write_text("synthetic-infra-probe", encoding="utf-8")
        assert path.read_text(encoding="utf-8") == "synthetic-infra-probe", folder
    # Separate SQLite fixture in the queue volume: never insert jobs to be consumed.
    path = Path("data/store_publish/.infra-persistence.sqlite3")
    if args.mode == "verify":
        assert path.is_file()
    with sqlite3.connect(path) as conn:
        if args.mode == "write":
            conn.execute("CREATE TABLE IF NOT EXISTS probe (id INTEGER PRIMARY KEY, value TEXT)")
            conn.execute("INSERT OR IGNORE INTO probe VALUES (1, 'synthetic')")
        assert conn.execute("SELECT value FROM probe WHERE id=1").fetchone() == ("synthetic",)
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    with create_engine(url).begin() as conn:
        if args.mode == "write":
            conn.execute(text("CREATE TABLE IF NOT EXISTS infra_persistence_probe (id INTEGER PRIMARY KEY, value TEXT)"))
            conn.execute(text("INSERT INTO infra_persistence_probe VALUES (1, 'synthetic') ON CONFLICT DO NOTHING"))
        assert conn.scalar(text("SELECT value FROM infra_persistence_probe WHERE id=1")) == "synthetic"
    print("Persistência OK: 10 volumes de arquivos, SQLite e PostgreSQL isolados.")


if __name__ == "__main__":
    main()
