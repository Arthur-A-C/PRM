"""Deactivate a named non-manager test account and revoke its sessions."""

import argparse
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import LoginSession, User
from app.services.security import normalize_email


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email", help="E-mail individual do usuário de teste")
    args = parser.parse_args()
    with Session(get_engine()) as db, db.begin():
        user = db.scalar(select(User).where(User.email == normalize_email(args.email)))
        if user is None or user.role != "vendedor":
            raise SystemExit("Usuário vendedor não encontrado; nenhum gestor foi alterado.")
        user.active = False
        db.execute(update(LoginSession).where(
            LoginSession.user_id == user.id,
            LoginSession.revoked_at.is_(None),
        ).values(revoked_at=datetime.now(timezone.utc)))
    print("Usuário de teste desativado e sessões revogadas.")


if __name__ == "__main__":
    main()
