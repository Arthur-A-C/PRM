"""Cold backup of Docker files only; never reads Windows or dumps production DB."""
from datetime import datetime, timezone
from pathlib import Path
import tarfile

if __name__ == "__main__":
    destination = Path("data/backups") / ("docker-files-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".tar.gz")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, "x:gz") as archive:
        for folder in Path("data").iterdir():
            if folder.name != "backups":
                archive.add(folder, arcname=folder.name)
    print(f"Backup de arquivos Docker: {destination.name}. PostgreSQL exige pg_dump separado.")
