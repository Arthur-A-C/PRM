"""Restore the image/_wcda_arquivos links removed from one product. Never deletes media.

Production requires a single-use 'restore_<mode>' grant:
    python scripts/homologation_grant.py issue-removal --batch <lote> --sku <SKU> --restore --confirm "AUTORIZO restaurar <SKU>"
    python scripts/store_removal_restore.py --batch <lote> --sku <SKU>
"""
import argparse
import getpass
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.store_config import StoreSettings
from app.services.store_file_removal import restore_one
from app.services.store_registration_jobs import Jobs


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--sku", required=True)
    args = parser.parse_args()
    print(json.dumps(restore_one(Jobs(), StoreSettings(), args.batch, args.sku, actor="cli:" + getpass.getuser()), ensure_ascii=False))


if __name__ == "__main__":
    main()
