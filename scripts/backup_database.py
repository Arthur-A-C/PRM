import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from app.config import get_settings


def find_pg_dump() -> Path:
    executable = shutil.which("pg_dump")
    if executable:
        return Path(executable)
    candidates = sorted(
        Path("C:/Program Files/PostgreSQL").glob("*/bin/pg_dump.exe"), reverse=True
    )
    if not candidates:
        raise SystemExit("pg_dump não encontrado.")
    return candidates[0]


def main() -> None:
    database_url = get_settings().database_url
    if not database_url:
        raise SystemExit("Banco não configurado.")
    url = make_url(database_url)
    destination_dir = Path("data/backups")
    destination_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = destination_dir / f"{url.database}_{timestamp}.dump"
    environment = os.environ.copy()
    if url.password:
        environment["PGPASSWORD"] = url.password
    command = [
        str(find_pg_dump()),
        "--host", str(url.host or "127.0.0.1"),
        "--port", str(url.port or 5432),
        "--username", str(url.username or ""),
        "--dbname", str(url.database or ""),
        "--format", "custom",
        "--no-owner",
        "--no-privileges",
        "--file", str(destination),
    ]
    result = subprocess.run(command, env=environment, capture_output=True, text=True)
    if result.returncode != 0:
        destination.unlink(missing_ok=True)
        raise SystemExit("Falha no pg_dump; nenhum backup válido foi mantido.")
    print(f"Backup criado: {destination} ({destination.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

