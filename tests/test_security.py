import pytest

from app.services.security import (
    hash_password,
    hash_secret,
    normalize_email,
    secrets_match,
    verify_password,
)


def test_password_round_trip() -> None:
    password_hash = hash_password("uma-senha-segura-123")
    assert verify_password(password_hash, "uma-senha-segura-123")
    assert not verify_password(password_hash, "senha-errada")


def test_short_password_is_rejected() -> None:
    with pytest.raises(ValueError, match="6 caracteres"):
        hash_password("curta")
    assert verify_password(hash_password("123456"), "123456")


def test_secret_comparison_and_email_normalization() -> None:
    assert secrets_match(hash_secret("csrf"), "csrf")
    assert not secrets_match(hash_secret("csrf"), "outro")
    assert normalize_email(" Gestor@Empresa.COM ") == "gestor@empresa.com"

