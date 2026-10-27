"""Identity stand-in for existing file-processing unit tests, not security integration tests."""
import pytest
from app.services import store_registration_authorization as authorization


@pytest.fixture
def mocked_registration_identity(monkeypatch):
    # These legacy fixtures use 'org'/'owner', not persisted UUIDs. Real identity/role/org
    # checks are exercised without this fixture in test_store_registration_roles.py.
    monkeypatch.setattr(authorization, "check_identity", lambda *args, **kwargs: None)
