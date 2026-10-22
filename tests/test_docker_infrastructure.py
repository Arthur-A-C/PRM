"""Infrastructure contracts without Docker, credentials or private fixtures."""
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_compose_is_isolated_and_has_all_workers():
    path = ROOT / "compose.yaml"
    if not path.exists():
        pytest.skip("Compose control file intentionally excluded from runtime image")
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    services = config["services"]
    assert config["networks"]["isolated"]["internal"] is True
    assert services["gateway"]["ports"] == ["127.0.0.1:${PRM_DOCKER_PORT:-8001}:8000"]
    assert "ports" not in services["api"]
    assert "ports" not in services["db"]
    assert services["db"]["volumes"] == ["postgres:/var/lib/postgresql"]
    for name in ("api", "worker-registration", "worker-removal", "worker-datasheets", "worker-alerts"):
        service = services[name]
        assert "env_file" not in service
        assert service["environment"]["PRM_DATABASE_URL"].endswith("@db:5432/prm_docker")
        assert service["environment"]["PRM_PUBLISH_ENABLED"] == "false"
        assert all(not v.startswith((".", "/", "C:")) for v in service["volumes"])


def test_migration_refuses_production():
    result = subprocess.run([sys.executable, str(ROOT / "docker/migrate.py")],
        env={**os.environ, "PRM_DATABASE_URL": "postgresql://localhost/prm_mvp"},
        capture_output=True, text=True)
    assert result.returncode != 0
    assert "prm_docker" in result.stderr


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX flock is enforced by Linux container")
def test_worker_refuses_production_and_duplicate_queue(tmp_path):
    import fcntl
    script = ROOT / "docker/worker.py"
    env = {**os.environ, "PRM_DOCKER_WORKERS_ENABLED": "true",
           "PRM_DATABASE_URL": "postgresql://localhost/prm_mvp"}
    result = subprocess.run([sys.executable, str(script), "registration"], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "Windows preservado" in result.stderr
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/store_registration_worker.py").write_text("raise AssertionError('must not start')")
    directory = tmp_path / "data/store_publish"
    directory.mkdir(parents=True)
    env["PRM_DATABASE_URL"] = "postgresql://db/prm_docker"
    with (directory / ".registration.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = subprocess.run([sys.executable, str(script), "registration"], cwd=tmp_path,
                                env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "Já existe worker" in result.stderr
