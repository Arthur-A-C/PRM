"""Transcribe locally; emits JSON. Provision model separately, never during upload."""
import argparse
import json
from app.services.meeting_asr import transcribe_local


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio")
    parser.add_argument("--model", default="small")
    parser.add_argument("--cache", default="data/meetings/models")
    parser.add_argument("--language", default="pt")
    parser.add_argument("--max-duration", type=int, default=14400)
    parser.add_argument("--memory-mib", type=int, default=4096)
    args = parser.parse_args()
    from app.services.meeting_resources import limit_memory
    limit_memory(args.memory_mib)
    result = transcribe_local(args.audio, model=args.model, cache=args.cache, language=args.language, max_duration=args.max_duration)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
