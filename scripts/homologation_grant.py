"""Issue, list or revoke a single-use production homologation grant. Run only by the operator.

A grant never performs a write by itself. It lets the registration worker send one approved
Dry Run (or one rollback) for the hard-coded target in store_publish_grant.HOMOLOGATION_TARGETS.

    python scripts/homologation_grant.py list
    python scripts/homologation_grant.py issue --batch <lote> --sku 119002000072 --product-id 16321 \
        --dry-run-sha256 <hash> --purpose publish --minutes 30 --confirm "AUTORIZO publish 119002000072"
    python scripts/homologation_grant.py issue-scope --batch <lote> --sku 119002000072 [--sku ...] --max-items 5
        --minutes 30 --confirm "AUTORIZO publish 1 itens"
    python scripts/homologation_grant.py issue-removal --batch <lote de remoção> --sku 119002000072 --minutes 30 \
        --confirm "AUTORIZO remover 119002000072"   [--restore com --confirm "AUTORIZO restaurar 119002000072"]
    python scripts/homologation_grant.py revoke --id <grant>

issue-scope creates one single-use grant per SKU under a shared scope (all-or-nothing). Every SKU must
still be an allowed homologation target; a scope never widens what a single grant can unlock.
"""
import argparse
import getpass
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import store_publish_grant as grants
from app.services.store_registration_jobs import Jobs


def stamp(value):
    return datetime.fromtimestamp(value).strftime("%d/%m/%Y %H:%M:%S") if value else ""


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    issue = sub.add_parser("issue")
    issue.add_argument("--batch", required=True)
    issue.add_argument("--sku", required=True)
    issue.add_argument("--product-id", type=int, required=True)
    issue.add_argument("--dry-run-sha256", required=True)
    issue.add_argument("--purpose", choices=sorted(grants.PURPOSES), required=True)
    issue.add_argument("--minutes", type=int, default=30)
    issue.add_argument("--confirm", required=True, help='Texto exato: "AUTORIZO <purpose> <sku>"')
    scope = sub.add_parser("issue-scope")
    scope.add_argument("--batch", required=True)
    scope.add_argument("--sku", action="append", required=True)
    scope.add_argument("--max-items", type=int, required=True)
    scope.add_argument("--minutes", type=int, default=30)
    scope.add_argument("--confirm", required=True, help='Texto exato: "AUTORIZO publish <n> itens"')
    removal = sub.add_parser("issue-removal")
    removal.add_argument("--batch", required=True)
    removal.add_argument("--sku", required=True)
    removal.add_argument("--minutes", type=int, default=30)
    removal.add_argument("--restore", action="store_true")
    removal.add_argument("--confirm", required=True, help='Texto exato: "AUTORIZO remover <sku>" ou "AUTORIZO restaurar <sku>"')
    revoke = sub.add_parser("revoke")
    revoke.add_argument("--id", required=True)
    args = parser.parse_args()
    jobs = Jobs()
    actor = "cli:" + getpass.getuser()
    if args.command == "list":
        for g in grants.listing(jobs):
            print(json.dumps({**g, "created": stamp(g["created"]), "expires": stamp(g["expires"]), "consumed": stamp(g["consumed"])}, ensure_ascii=False))
        return
    if args.command == "revoke":
        grants.revoke(jobs, args.id, actor)
        print("Liberação revogada.")
        return
    if args.command == "issue-removal":
        expected = f"AUTORIZO {'restaurar' if args.restore else 'remover'} {args.sku}"
        if args.confirm != expected:
            raise SystemExit(f'Confirmação incorreta. Digite exatamente: --confirm "{expected}"')
        from app.services.store_file_removal import Removals
        Removals(jobs)  # removal tables exist before validation
        grant = grants.issue_removal(jobs, batch=args.batch, sku=args.sku, minutes=args.minutes, actor=actor, restore=args.restore)
        print(json.dumps({"id": grant["id"], "purpose": grant["purpose"], "sku": grant["sku"], "product_id": grant["product_id"],
                          "expires": stamp(grant["expires"]), "uso": "único"}, ensure_ascii=False))
        return
    if args.command == "issue-scope":
        count = len(dict.fromkeys(args.sku))
        if args.confirm != f"AUTORIZO publish {count} itens":
            raise SystemExit(f'Confirmação incorreta. Digite exatamente: --confirm "AUTORIZO publish {count} itens"')
        result = grants.issue_scope(jobs, batch=args.batch, skus=args.sku, minutes=args.minutes, actor=actor, max_items=args.max_items)
        for g in result["grants"]:
            print(json.dumps({"scope": result["scope"], "id": g["id"], "sku": g["sku"], "product_id": g["product_id"],
                              "expires": stamp(g["expires"]), "uso": "único"}, ensure_ascii=False))
        return
    if args.confirm != f"AUTORIZO {args.purpose} {args.sku}":
        raise SystemExit(f'Confirmação incorreta. Digite exatamente: --confirm "AUTORIZO {args.purpose} {args.sku}"')
    grant = grants.issue(jobs, batch=args.batch, sku=args.sku, product_id=args.product_id,
                         dry_run_sha256=args.dry_run_sha256, purpose=args.purpose, minutes=args.minutes, actor=actor)
    print(json.dumps({"id": grant["id"], "purpose": grant["purpose"], "origin": grant["origin"], "sku": grant["sku"],
                      "product_id": grant["product_id"], "expires": stamp(grant["expires"]), "uso": "único"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
