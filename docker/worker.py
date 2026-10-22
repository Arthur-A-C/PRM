"""Linux worker guard: one instance per queue/stage; no production DB workers."""
import fcntl
import os
from pathlib import Path
import runpy
import sys
from urllib.parse import urlsplit

WORKERS = {
    "registration": ("scripts/store_registration_worker.py", "store_publish"),
    "removal": ("scripts/store_removal_worker.py", "store_publish"),
    "datasheets": ("scripts/datasheet_batch_worker.py", "datasheet_batches"),
    "alerts": ("scripts/meeting_worker.py", "meetings"),
}


def main():
    role = sys.argv[1] if len(sys.argv) > 1 else ""
    if role not in WORKERS:
        raise SystemExit("Worker desconhecido.")
    db = urlsplit(os.environ.get("PRM_DATABASE_URL", ""))
    if (os.environ.get("PRM_DOCKER_WORKERS_ENABLED") != "true"
            or db.hostname != "db" or db.path != "/prm_docker"):
        raise SystemExit("Workers Docker limitados ao banco isolado prm_docker; Windows preservado.")
    script, folder = WORKERS[role]
    if not Path(script).is_file():
        raise SystemExit(f"Dependência funcional não versionada/ausente: {script}. Integre o PR funcional antes de ativar este worker.")
    directory = Path("data") / folder
    directory.mkdir(parents=True, exist_ok=True)
    # Keep the descriptor open for the lifetime of the Python worker (including threads).
    with (directory / f".{role}.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(f"Já existe worker {role} usando este volume.") from None
        sys.path.insert(0, str(Path.cwd()))
        sys.argv = [script, *( ["--stage", "alerts"] if role == "alerts" else []), *sys.argv[2:]]
        print(f"Worker {role}: fila isolada; lock adquirido.", flush=True)
        runpy.run_path(script, run_name="__main__")


if __name__ == "__main__":
    main()
