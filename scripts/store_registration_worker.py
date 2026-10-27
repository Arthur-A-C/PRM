"""Files worker: active role, organization, approved Dry Run and persisted explicit confirmation."""
import sys
import time
import argparse
import os
import subprocess
import threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.store_config import StoreSettings
from app.services.store_registration_jobs import Jobs, process_one


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--once",action="store_true")
    # Restrict processing to exactly one confirmed item; other batches stay untouched.
    parser.add_argument("--batch")
    parser.add_argument("--sku")
    parser.add_argument("--child",action="store_true",help=argparse.SUPPRESS)
    args=parser.parse_args()
    if bool(args.batch)!=bool(args.sku): parser.error("--batch e --sku devem ser informados juntos.")
    target=["--batch",args.batch,"--sku",args.sku] if args.batch else []
    jobs=Jobs()
    if args.child:
        watchdog=threading.Timer(3300,lambda:os._exit(124))
        watchdog.daemon=True;watchdog.start()
        try: process_one(jobs,StoreSettings(),batch=args.batch,sku=args.sku)
        finally: watchdog.cancel()
        return
    try:
        while True:
            try:
                subprocess.run([sys.executable,str(Path(__file__).resolve()),"--child",*target],
                    timeout=3320,check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            except subprocess.TimeoutExpired:
                print("Worker interrompido por timeout; item será marcado para reconciliação.")
            if args.once: break
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    if args.batch:
        # State and sanitized error only; never plan paths, payloads or credentials.
        with jobs.db() as db:
            row=db.execute("SELECT state,error FROM jobs WHERE batch=? AND sku=?",(args.batch,args.sku)).fetchone()
        print(f"{args.sku}: {row['state']} {row['error']}".strip() if row else "Item não encontrado no lote.")


if __name__=="__main__": main()
