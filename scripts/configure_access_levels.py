"""Audit by default. Explicit --apply migrates roles and promotes only supplied IDs atomically."""
import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text, update
from app.db import get_engine
from app.models import User, Organization


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--organization',type=uuid.UUID,required=True)
    parser.add_argument('--user',type=uuid.UUID,action='append',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args(); identifiers=set(args.user)
    with get_engine().begin() as conn:
        if not args.apply:
            conn.execute(text('SET TRANSACTION READ ONLY'))
        else:
            conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        if not conn.scalar(select(Organization.id).where(Organization.id==args.organization)):
            raise RuntimeError('Organização inexistente.')
        query=select(User.id,User.role).where(User.organization_id==args.organization,User.id.in_(identifiers),User.active.is_(True))
        if args.apply: query=query.with_for_update()
        users=conn.execute(query).all()
        if {u.id for u in users}!=identifiers or any(u.role not in {'gestor','desenvolvedor'} for u in users):
            raise RuntimeError('IDs, organização ou níveis não correspondem à auditoria; nenhuma alteração autorizada.')
        print('Contas verificadas:',len(users))
        if args.apply:
            cfg=Config('alembic.ini');cfg.attributes['connection']=conn
            command.upgrade(cfg,'20261021_0010')
            conn.execute(update(User).where(User.id.in_(identifiers),User.organization_id==args.organization).values(role='desenvolvedor'))
            print('Migração específica e conversão aplicadas na mesma transação; reuniões não migradas.')
        else:
            print('Somente auditoria. Use --apply para executar.')


if __name__=='__main__':
    try: main()
    except Exception:
        print('Operação cancelada; detalhes técnicos omitidos para proteger a conexão. Nenhuma transação parcial foi mantida.')
        raise SystemExit(1)
