from getpass import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine
from app.models import User
from app.services.bootstrap import ensure_reference_data
from app.services.security import hash_password, normalize_email


def main() -> None:
    settings = get_settings()
    print("Criação segura do primeiro gestor PRM")
    name = input("Nome: ").strip()
    email = normalize_email(input("E-mail: "))
    password = getpass("Senha (mínimo de 12 caracteres): ")
    confirmation = getpass("Repita a senha: ")
    if not name or not email:
        raise SystemExit("Nome e e-mail são obrigatórios.")
    if password != confirmation:
        raise SystemExit("As senhas não coincidem.")
    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    with Session(get_engine()) as db, db.begin():
        if db.scalar(select(User).where(User.email == email)):
            raise SystemExit("Já existe um usuário com esse e-mail.")
        organization, _ = ensure_reference_data(db, settings)
        db.add(
            User(
                organization_id=organization.id,
                name=name,
                email=email,
                password_hash=password_hash,
                role="gestor",
                active=True,
            )
        )
    print("Gestor e cadastros iniciais criados com sucesso.")


if __name__ == "__main__":
    main()
