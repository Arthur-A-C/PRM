"""Local ASR process. Only the optional ASR environment imports native dependencies."""
import json
import os
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def model_instance(model, cache):
    from faster_whisper import WhisperModel
    if model.endswith(".en"):
        raise ValueError("Modelo .en não suporta transcrição em português")
    return WhisperModel(model, device="cpu", compute_type="int8", download_root=cache,
                        cpu_threads=2, num_workers=1, local_files_only=True)


def transcribe_local(path, *, model="small", cache="data/meetings/models", language="pt", max_duration=14400):
    import av
    started = time.monotonic()
    # Fully inspect the decoded timeline before inference; reject unbounded/false media.
    duration = 0.0
    with av.open(str(path)) as media:
        if not media.streams.audio:
            raise ValueError("Arquivo não contém faixa de áudio")
        stream = media.streams.audio[0]
        for frame in media.decode(stream):
            duration += frame.samples / frame.sample_rate
            if duration > max_duration:
                raise ValueError("Áudio excede a duração permitida")
    if not duration:
        raise ValueError("Áudio vazio")
    segments, info = model_instance(model, str(cache)).transcribe(str(path), language=None if language == "auto" else language,
        task="transcribe", vad_filter=True, beam_size=5, condition_on_previous_text=False)
    output, questionable = [], False
    for index, segment in enumerate(segments, 1):
        content = segment.text.strip()
        if not content:
            continue
        if segment.avg_logprob < -1.0 or segment.no_speech_prob > .6:
            questionable = True
        output.append({"ordinal": index, "text": content, "start_ms": round(segment.start * 1000),
                       "end_ms": round(segment.end * 1000), "participant_id": None, "speaker": None,
                       "timestamp": f"{int(segment.start)//60}:{int(segment.start)%60:02}", "alignment": "asr"})
    if not output:
        raise ValueError("Nenhuma fala útil detectada; não analisar silêncio")
    return {"segments": output, "duration_seconds": duration, "language": info.language,
            "elapsed_seconds": round(time.monotonic() - started, 3), "complete": True,
            "needs_review": questionable, "model": model, "device": "cpu", "compute_type": "int8",
            "warning": "ASR não identifica pessoas; revise nomes, datas e números."}


def transcribe_process(path, settings):
    separate = Path('.venv-asr/Scripts/python.exe' if os.name == 'nt' else '.venv-asr/bin/python')
    python = settings.asr_python or (str(separate.resolve()) if separate.is_file() else sys.executable)
    arguments = [python, "-m", "scripts.transcribe_audio", str(path), "--model", settings.asr_model,
                 "--cache", str(Path(settings.asr_model_cache_dir).resolve()), "--language", settings.asr_language,
                 "--max-duration", str(settings.audio_max_duration_seconds), "--memory-mib", str(settings.asr_memory_mib)]
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    try:
        completed = subprocess.run(arguments, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   timeout=settings.asr_timeout_seconds, check=False, **options)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Transcrição interrompida pelo limite de tempo; análise não iniciada") from exc
    if completed.returncode:
        raise ValueError("ASR local indisponível/falhou. Confira ambiente, modelo provisionado, codec e limites; nenhum texto parcial foi publicado")
    return json.loads(completed.stdout)
