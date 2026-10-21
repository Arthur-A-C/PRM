"""Durable meeting worker. ASR is serialized by a PostgreSQL advisory lock."""
import argparse
import time
from sqlalchemy import text, select
from sqlalchemy.orm import Session
from app.config import get_settings
from app.db import get_engine
from app.models.meetings import Activity
from app.services.meeting_worker import process_next
from app.services.meeting_activities import sync_alerts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["analysis", "cards", "transcription", "alerts", "text"], default="text")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    engine, settings = get_engine(), get_settings()
    with engine.connect() as lock:
        if not lock.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": 16102600 + ["analysis", "cards", "transcription", "alerts", "text"].index(args.stage)}):
            raise RuntimeError("Já existe worker desta fila")
        try:
            while True:
                if args.stage == "alerts":
                    with Session(engine) as db, db.begin():
                        for activity in db.scalars(select(Activity).where(Activity.approval == "published").with_for_update()).yield_per(100):
                            sync_alerts(db, activity)
                else:
                    for stage in (["analysis", "cards"] if args.stage == "text" else [args.stage]):
                        process_next(engine, settings, stage)
                if args.once:
                    break
                time.sleep(60 if args.stage == "alerts" else 2)
        finally:
            lock.execute(text("SELECT pg_advisory_unlock_all()"))


if __name__ == "__main__":
    main()
