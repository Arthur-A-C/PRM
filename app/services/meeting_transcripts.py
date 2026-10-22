"""Deterministic segmentation; unknown speakers are never merged into a person."""
import hashlib
import re

HEADER = re.compile(r"^(\d{1,3}:\d{2}(?::\d{2})?)\s*[-–]\s*(.+?)\s*$", re.M)


def parse_transcript(text: str, revision: str) -> tuple[list[dict], list[dict]]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    matches = list(HEADER.finditer(text))
    chunks = []
    if matches:
        if text[:matches[0].start()].strip():
            chunks.append((None, None, text[:matches[0].start()].strip()))
        for i, match in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            chunks.append((match[1], match[2], text[match.end():end].strip()))
    else:
        chunks = [(None, None, t.strip()) for t in re.split(r"\n\s*\n", text) if t.strip()]
    participants, names, segments = [], {}, []
    for ordinal, (timestamp, speaker, content) in enumerate(chunks, 1):
        if not content:
            continue
        participant = None
        if speaker and speaker.casefold() != "falante não identificado":
            if speaker not in names:
                names[speaker] = f"p{len(names) + 1}"
                participants.append({"id": names[speaker], "name": speaker, "kind": "unconfirmed", "user_id": None})
            participant = names[speaker]
        seconds = None
        if timestamp:
            seconds = 0
            for part in timestamp.split(":"):
                seconds = seconds * 60 + int(part)
        segments.append({"id": f"{revision}-s{ordinal:04}", "ordinal": ordinal, "speaker": speaker,
                         "participant_id": participant, "timestamp": timestamp,
                         "start_ms": seconds * 1000 if seconds is not None else None,
                         "end_ms": None, "text": content, "alignment": "source"})
    if not segments:
        raise ValueError("Transcrição vazia")
    return segments, participants


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
