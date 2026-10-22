"""Restore images and _wcda_arquivos of one published item. Never deletes media from the library.

Production requires a single-use 'rollback' grant (scripts/homologation_grant.py). The restore runs
only if the product is exactly in the post-publish state recorded in the journal.

    python scripts/store_registration_rollback.py --batch <lote> --sku 119002000072
"""
import argparse
import getpass
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.store_config import StoreSettings
from app.services.store_registration_jobs import Jobs, rollback_one


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--sku", required=True)
    args = parser.parse_args()
    result = rollback_one(Jobs(), StoreSettings(), args.batch, args.sku, actor="cli:" + getpass.getuser())
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
