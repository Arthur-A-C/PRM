"""Durable registration worker. Production writes hard-blocked by publisher policy."""
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
    parser.add_argument("--child",action="store_true",help=argparse.SUPPRESS)
    args=parser.parse_args()
    jobs=Jobs()
    if args.child:
        watchdog=threading.Timer(900,lambda:os._exit(124))
        watchdog.daemon=True;watchdog.start()
        try: process_one(jobs,StoreSettings())
        finally: watchdog.cancel()
        return
    try:
        while True:
            try:
                subprocess.run([sys.executable,str(Path(__file__).resolve()),"--child"],
                    timeout=920,check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            except subprocess.TimeoutExpired:
                print("Worker interrompido por timeout; item será marcado para reconciliação.")
            if args.once: break
            time.sleep(2)
    except KeyboardInterrupt:
        pass


if __name__=="__main__": main()
