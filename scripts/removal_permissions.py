"""Bootstrap of the first Remoção de arquivos administrator (one-time, at deployment).

Day-to-day permissions are managed in the UI by administrators. This only grants the administration
permission to an existing, active "desenvolvedor"; it never enables production (that stays a UI action
behind PRM_REMOVAL_PRODUCTION_ALLOWED=true, HTTPS and a successful store preflight).

    python scripts/removal_permissions.py list
    python scripts/removal_permissions.py grant-admin --email dev@empresa.com.br --companies choice,portwell,sag
"""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models.identity import User
from app.models.store_operations import STORE_COMPANIES, StoreOperationPermission
from app.services import store_removal_production as production
from app.services.store_registration_jobs import Jobs


def grant_admin(db, email, companies, actor, jobs=None):
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not user.active:
        raise SystemExit("Usuário não encontrado ou inativo.")
    if user.role != "desenvolvedor":
        raise SystemExit("A administração da remoção exige o papel desenvolvedor.")
    for company in companies:
        row = db.scalar(select(StoreOperationPermission).where(StoreOperationPermission.user_id == user.id,
                                                               StoreOperationPermission.company == company))
        if row is None:
            row = StoreOperationPermission(organization_id=user.organization_id, user_id=user.id, company=company)
            db.add(row)
        row.can_admin = True
        row.granted_by_id = None
    db.commit()
    jobs = jobs or Jobs()
    for company in companies:
        jobs.audit("permissoes:" + company, "", actor, "permission_bootstrap", {"user": str(user.id), "admin": True})
    return user


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    grant = sub.add_parser("grant-admin")
    grant.add_argument("--email", required=True)
    grant.add_argument("--companies", default=",".join(STORE_COMPANIES))
    args = parser.parse_args()
    with Session(get_engine()) as db:
        if args.command == "list":
            for user in db.scalars(select(User).where(User.active.is_(True))).all():
                perms = production.summary(db, user)
                granted = {c: [a for a, v in p.items() if v] for c, p in perms.items() if any(p.values())}
                if granted:
                    print(f"{user.email} ({user.role}): {granted}")
            return
        companies = [c.strip() for c in args.companies.split(",") if c.strip()]
        if not companies or any(c not in STORE_COMPANIES for c in companies):
            raise SystemExit("Empresas válidas: " + ", ".join(STORE_COMPANIES))
        user = grant_admin(db, args.email, companies, "cli:" + getpass.getuser())
        print(f"Administração da remoção concedida a {user.email} em: {', '.join(companies)}. Produção continua desligada.")


if __name__ == "__main__":
    main()
