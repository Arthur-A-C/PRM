"""Manual schema initialization restricted to the disposable Docker database."""
import os
import subprocess
from urllib.parse import urlsplit

if __name__ == "__main__":
    db = urlsplit(os.environ.get("PRM_DATABASE_URL", ""))
    if db.hostname != "db" or db.path != "/prm_docker":
        raise SystemExit("Migração recusada: somente db/prm_docker é permitido neste comando.")
    subprocess.run(["alembic", "upgrade", "head"], check=True)
