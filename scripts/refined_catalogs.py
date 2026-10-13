"""python -m scripts.refined_catalogs profile|run|publish --manifest ARQUIVO"""

import argparse
import json
import platform
from pathlib import Path

from app.services.refined_catalog import STAGING, load_inputs, load_policy, profile_inputs, publish_analysis, run_pipeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["profile", "run", "publish"])
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--input-dir", type=Path, help="Alternativa ao manifesto para os quatro nomes recebidos")
    parser.add_argument("--run-id")
    parser.add_argument("--output-root", type=Path, default=STAGING)
    parser.add_argument("--dry-run", action="store_true", help="Só perfila; não copia, publica, chama IA ou SQL")
    args = parser.parse_args()
    if args.command == "publish":
        if args.dry_run or not args.run_id:
            parser.error("publish exige --run-id e não aceita --dry-run")
        result = publish_analysis(args.run_id, args.output_root)
        print(json.dumps({"published_analysis": result["run_id"], "database_modified": False}))
        return
    if bool(args.manifest) == bool(args.input_dir):
        parser.error("Informe --manifest OU --input-dir")
    entries = load_inputs(args.manifest) if args.manifest else [
        {"source_id": source, "path": (args.input_dir / filename).resolve(strict=True)}
        for source, filename in [("portwell", "produtos-portwell.csv"), ("choice", "produtos-choice.csv"),
                                 ("eco", "Produtos_ECO_Tratados_PRM.xlsx"), ("dimensional", "produtos_dimensional.csv")]
    ]
    policy = load_policy()
    if args.command == "profile" or args.dry_run:
        print(json.dumps(profile_inputs(entries, policy), ensure_ascii=False, indent=2))
    else:
        result = run_pipeline(entries, policy, output_root=args.output_root)
        print(json.dumps({"run_id": result["run_id"], "idempotent": result["idempotent"], "counts": result["counts"], "elapsed_seconds": result["elapsed_seconds"], "python": platform.python_version(), "platform": platform.platform()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
