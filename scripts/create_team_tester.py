"""Create a named, non-manager PRM account for a trusted remote teammate."""

from getpass import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Organization, User
from app.services.security import hash_password, normalize_email


def main() -> None:
    name = input("Nome do colega: ").strip()
    email = normalize_email(input("E-mail individual: "))
    password = getpass("Senha individual (mínimo 6 caracteres): ")
    confirmation = getpass("Repita a senha: ")
    if not name or not email or "@" not in email:
        raise SystemExit("Nome e e-mail individual válido são obrigatórios.")
    if password != confirmation:
        raise SystemExit("As senhas não coincidem.")
    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    with Session(get_engine()) as db, db.begin():
        organizations = db.scalars(select(Organization)).all()
        if len(organizations) != 1:
            raise SystemExit("É necessário selecionar a organização explicitamente antes de criar o usuário.")
        if db.scalar(select(User.id).where(User.email == email)):
            raise SystemExit("Já existe um usuário com esse e-mail.")
        db.add(User(
            organization_id=organizations[0].id,
            name=name,
            email=email,
            password_hash=password_hash,
            role="vendedor",
            active=True,
        ))
    print("Usuário vendedor criado. Compartilhe a senha individual por canal seguro.")


if __name__ == "__main__":
    main()
