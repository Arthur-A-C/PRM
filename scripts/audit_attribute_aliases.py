"""Auditoria reproduzível dos atributos de um snapshot, sem escrita no banco."""

import argparse
import json
from collections import Counter

from app.services.refined_catalog import STAGING, verify_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    manifest = verify_run(STAGING / args.run_id)
    names, mappings, samples = Counter(), Counter(), {}
    with (STAGING / args.run_id / 'attribute_observations.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            attr = json.loads(line)
            source = attr['evidence'][0]['source_id']
            key = (source, attr['raw_name'], attr['attribute_code'])
            names[key] += 1
            mappings[(source, bool(attr['mapped']))] += 1
            samples.setdefault(key, attr['raw_value'])
    print(json.dumps({'run_id': args.run_id, 'rule_version': manifest['rule_version'],
                     'counts': manifest['counts'],
                     'aliases': [{'source': s, 'original_name': n, 'canonical_code': c,
                                  'observations': count, 'sample': samples[(s, n, c)]}
                                 for (s, n, c), count in names.most_common()],
                     'mapped': {s: mappings[(s, True)] for s in manifest['counts']}}, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
