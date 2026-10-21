"""Durable leased jobs; expensive work is outside web requests and DB transactions."""
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.models.meetings import Meeting, MeetingRun, MeetingAudio, TranscriptRevision
from app.schemas.meetings import validate_extraction
from app.services.meeting_pipeline import build_cards, enqueue, analysis_context
from app.services.meeting_transcripts import digest


def process_next(engine, settings, stage="analysis", extractor=None, transcriber=None):
    now = datetime.now(timezone.utc)
    with Session(engine) as db, db.begin():
        # Expired work is visibly failed, not automatically rebilled after an uncertain timeout.
        db.execute(update(MeetingRun).where(MeetingRun.state == "running", MeetingRun.lease_until < now)
                   .values(state="failed", error="Worker interrompido; revise antes de tentar novamente", finished_at=now))
        run = db.scalar(select(MeetingRun).where(MeetingRun.state == "queued", MeetingRun.stage == stage)
                        .order_by(MeetingRun.created_at).with_for_update(skip_locked=True).limit(1))
        if not run:
            return False
        run.state, run.started_at = "running", now
        run.lease_until = now + timedelta(seconds=(settings.asr_timeout_seconds if stage == "transcription" else 900) + 300)
        run.attempts += 1
        identifier, context = run.id, dict(run.context)
        revision = db.get(TranscriptRevision, run.revision_id) if run.revision_id else None
        segments = list(revision.segments) if revision else []
        audio = db.get(MeetingAudio, uuid.UUID(context["audio_id"])) if stage == "transcription" else None
        audio_key = audio.storage_key if audio else None
    started = time.monotonic()
    raw = None
    try:
        if stage == "analysis":
            if context["provider"] == "fixture":
                if not settings.meeting_enable_fixture:
                    raise ValueError("Simulador desabilitado")
                from app.services.meeting_fixture import read_ai_example
                raw, usage = read_ai_example(segments), {"simulation": True, "input_tokens": 0, "output_tokens": 0}
            else:
                from app.services.meeting_pipeline import extract_with_api
                raw, usage = (extractor or extract_with_api)(context, segments, settings)
            result = validate_extraction(raw, segments, context["participants"]).model_dump(mode="json")
        elif stage == "transcription":
            from app.services.meeting_asr import transcribe_process
            root = Path(settings.meeting_storage_dir).resolve()
            path = (root / audio_key).resolve()
            if not path.is_relative_to(root):
                raise ValueError("Caminho de áudio inválido")
            result = (transcriber or transcribe_process)(path, settings)
            usage = {"asr": True}
        else:
            result, usage = {}, {}
        with Session(engine) as db, db.begin():
            run = db.scalar(select(MeetingRun).where(MeetingRun.id == identifier).with_for_update())
            if run.state != "running" or run.started_at.replace(tzinfo=timezone.utc) != now:
                return True  # Cancellation/expired lease wins, no new stage or draft.
            meeting = db.get(Meeting, run.meeting_id)
            if stage == "cards":
                parent = db.get(MeetingRun, run.predecessor_id)
                if parent.state == "cancelled":
                    raise ValueError("Análise cancelada")
                result = build_cards(db, parent)
            elif stage == "transcription":
                revision_id = uuid.uuid4()
                parsed = [{**s, "id": f"{revision_id}-s{i:04}"} for i, s in enumerate(result["segments"], 1)]
                transcript = "\n\n".join(f"{s['timestamp']} - Falante não identificado\n{s['text']}" for s in parsed)
                revision = TranscriptRevision(id=revision_id, meeting_id=meeting.id, author_id=meeting.creator_id,
                    source="asr", original=transcript, sha256=digest(transcript.encode()), segments=parsed,
                    quality={k: v for k, v in result.items() if k != "segments"})
                db.add(revision)
                db.flush()
                run.revision_id = revision_id
                db.get(MeetingAudio, uuid.UUID(context["audio_id"])).duration_seconds = round(result["duration_seconds"])
                if context.get("analyze_after") and result.get("complete") and not result.get("needs_review"):
                    enqueue(db, meeting, "analysis", analysis_context(meeting, revision, settings), revision_id=revision_id, predecessor_id=run.id)
            run.raw_output, run.result, run.state = raw, result, "succeeded"
            run.context = {**run.context, "usage": usage, "elapsed_seconds": round(time.monotonic() - started, 3)}
            run.finished_at = datetime.now(timezone.utc)
            if stage == "analysis":
                enqueue(db, meeting, "cards", {"generator": "cards-1"}, revision_id=run.revision_id, predecessor_id=run.id)
    except Exception as exc:
        with Session(engine) as db, db.begin():
            run = db.scalar(select(MeetingRun).where(MeetingRun.id == identifier).with_for_update())
            if run.state == "running" and run.started_at.replace(tzinfo=timezone.utc) == now:
                run.state, run.finished_at, run.raw_output = "failed", datetime.now(timezone.utc), raw
                # Never expose provider response/transcript/key in logs or API error messages.
                run.error = str(exc)[:450] if type(exc) is ValueError else f"Falha {type(exc).__name__}; confira configuração/contrato. Nada publicado."
    return True
