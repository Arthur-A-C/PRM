from fastapi.testclient import TestClient

from app.main import app
from app.services.preview_auth import PreviewBasicAuth


def test_preview_requires_independent_basic_auth() -> None:
    client = TestClient(PreviewBasicAuth(app, "temporary-secret-with-at-least-24-chars"))
    blocked = client.get("/api/v1/health/live")
    assert blocked.status_code == 401
    assert blocked.headers["www-authenticate"].startswith("Basic realm=")
    assert client.get("/static/css/app.css").status_code == 401
    assert client.get("/api/v1/health/live", auth=("prm-preview", "wrong-password")).status_code == 401
    allowed = client.get(
        "/api/v1/health/live", auth=("prm-preview", "temporary-secret-with-at-least-24-chars")
    )
    assert allowed.status_code == 200
    assert allowed.headers["cache-control"] == "no-store"
    assert allowed.headers["x-robots-tag"] == "noindex, nofollow"


def test_preview_rejects_short_shared_password() -> None:
    try:
        PreviewBasicAuth(app, "short")
    except ValueError:
        pass
    else:
        raise AssertionError("Senha fraca foi aceita.")
