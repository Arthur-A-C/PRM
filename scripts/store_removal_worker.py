"""Durable file-removal worker: Dry Run, execution, restore and read-only reconciliation.

Before each write the worker re-checks the persisted actor/approver's active role and organization,
the exact approved Dry Run and explicit confirmation. A verified backup is mandatory. Legacy grants,
per-store permission rows and environment switches do not authorize or block this removal-only flow.

    python scripts/store_removal_worker.py                      # continuous
    python scripts/store_removal_worker.py --once               # one item
    python scripts/store_removal_worker.py --once --batch <lote> --sku <SKU>   # exactly one authorized item
"""
import argparse
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.store_config import StoreSettings
from app.services.store_file_removal import process_one
from app.services.store_registration_jobs import Jobs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--batch")
    parser.add_argument("--sku")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if bool(args.batch) != bool(args.sku): parser.error("--batch e --sku devem ser informados juntos.")
    target = ["--batch", args.batch, "--sku", args.sku] if args.batch else []
    jobs = Jobs()
    if args.child:
        watchdog = threading.Timer(900, lambda: os._exit(124))
        watchdog.daemon = True; watchdog.start()
        try: process_one(jobs, StoreSettings(), batch=args.batch, sku=args.sku)
        finally: watchdog.cancel()
        return
    try:
        while True:
            try:
                subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child", *target], timeout=920, check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except subprocess.TimeoutExpired:
                print("Worker interrompido por timeout; item será marcado para reconciliação.")
            if args.once: break
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    if args.batch:
        with jobs.db() as db:
            row = db.execute("SELECT state,error FROM removal_items WHERE batch=? AND sku=?", (args.batch, args.sku)).fetchone()
        print(f"{args.sku}: {row['state']} {row['error']}".strip() if row else "Item não encontrado no lote.")


if __name__ == "__main__":
    main()
