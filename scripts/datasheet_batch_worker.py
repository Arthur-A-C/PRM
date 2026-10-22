"""Run from project root: python scripts/datasheet_batch_worker.py."""
import argparse
import json
import logging
import os
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from app.config import get_settings
from app.services.datasheet_batches import BatchStore, produce, run_once


def main():
    parser = argparse.ArgumentParser(description="Worker persistente de datasheets em lote")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--cleanup", action="store_true", help="Lista lotes expirados; não apaga por padrão")
    parser.add_argument("--apply", action="store_true", help="Com --cleanup, remove arquivos antigos; conserva histórico")
    parser.add_argument("--child", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    settings = get_settings()
    store = BatchStore(settings)
    logging.basicConfig(level=logging.INFO)
    if args.child:
        # Parent loss must not leave an unbounded orphan doing paid work.
        watchdog = threading.Timer(settings.batch_timeout_seconds, lambda: os._exit(124))
        watchdog.daemon = True
        watchdog.start()
        produce(store, json.loads(args.child.read_text(encoding="utf-8")))
        watchdog.cancel()
        return
    if args.cleanup:
        print(json.dumps({"applied": args.apply, "batches": store.cleanup(args.apply)}))
        return
    if args.once:
        run_once(store)
        return

    stopping = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())

    def loop():
        while not stopping.is_set():
            try:
                worked = run_once(store)
            except Exception as exc:
                logging.error("batch_worker error_type=%s", type(exc).__name__)
                worked = False
            if not worked:
                stopping.wait(3)

    with ThreadPoolExecutor(max_workers=settings.batch_concurrency) as pool:
        for _ in range(settings.batch_concurrency):
            pool.submit(loop)
        # Ctrl+C stops claims, waits for in-flight products (bounded by timeout).


if __name__ == "__main__":
    main()
