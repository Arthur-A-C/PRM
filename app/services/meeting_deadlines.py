"""Calendar-day rules are distinct from instants. Server timezone never participates."""
from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BUCKETS = ["atraso >30d", "atraso 8–30d", "atraso 1–7d", "venceu hoje", "hoje", "1d", "2d", "3–7d", "8–14d", "15–30d", ">30d"]


def deadline(activity, now=None):
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo(activity.timezone))
    if activity.approval != "published":
        return {"band": "draft", "bucket": None}
    if activity.status in {"done", "cancelled"}:
        return {"band": activity.status, "bucket": None}
    if not activity.due_date and not activity.due_at:
        return {"band": "no_deadline" if activity.no_deadline_accepted else "unconfirmed", "bucket": None}
    at = activity.due_at
    if at and at.tzinfo is None:  # SQLite test driver; PostgreSQL columns are timestamptz.
        at = at.replace(tzinfo=timezone.utc)
    due_day = activity.due_date or at.astimezone(ZoneInfo(activity.timezone)).date()
    days = (due_day - local.date()).days
    overdue = now > at if at else local.date() > due_day
    if overdue:
        bucket = "venceu hoje" if days == 0 else "atraso 1–7d" if days >= -7 else "atraso 8–30d" if days >= -30 else "atraso >30d"
        return {"band": "overdue", "bucket": bucket, "days": days}
    bucket = "hoje" if days == 0 else f"{days}d" if days <= 2 else "3–7d" if days <= 7 else "8–14d" if days <= 14 else "15–30d" if days <= 30 else ">30d"
    return {"band": "prioritize" if days <= 2 else "attention" if days <= 7 else "on_time", "bucket": bucket, "days": days}


def overview(activities, now=None):
    now = now or datetime.now(timezone.utc)
    values = [deadline(a, now) for a in activities if a.kind == "task"]
    counts = Counter(v["band"] for v in values)
    total = sum(counts[k] for k in ["on_time", "attention", "prioritize", "overdue"])
    histogram = Counter(v["bucket"] for v in values if v["bucket"])
    return {"updated_at": now.isoformat(), "denominator": total,
            "bands": {k: {"count": counts[k], "percent": round(100 * counts[k] / total, 1) if total else 0}
                      for k in ["on_time", "attention", "prioritize", "overdue"]},
            "no_deadline": counts["no_deadline"], "unconfirmed": counts["unconfirmed"],
            "histogram": [{"label": b, "count": histogram[b]} for b in BUCKETS]}
