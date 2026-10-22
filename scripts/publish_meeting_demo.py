"""Publish only a private, reversible dashboard mock. Database is read-only."""
import argparse
import json
import os
import tempfile
from pathlib import Path
from sqlalchemy import create_engine, select, text
from app.config import get_settings
from app.models import Organization
from app.services.meeting_demo import build_demo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transcript', type=Path, required=True)
    args = parser.parse_args()
    settings = get_settings()
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        conn.execute(text('SET TRANSACTION READ ONLY'))
        org_id = conn.execute(select(Organization.id).where(Organization.name == settings.organization_name)).scalar_one()
    result = build_demo(args.transcript.read_bytes(), org_id)
    root = Path(settings.meeting_storage_dir).resolve()
    if root.is_relative_to(Path('app/static').resolve()):
        raise ValueError('A demonstração deve ficar fora da pasta pública')
    root.mkdir(parents=True, exist_ok=True)
    target = root / 'read-ai-dashboard-demo.json'
    if target.exists():
        existing = json.loads(target.read_text(encoding='utf-8'))
        if existing.get('source_sha256') == result['source_sha256'] and existing.get('organization_id') == str(org_id):
            print('Mock já publicado; 7 cards preservados.'); return
        raise ValueError('Já existe outra demonstração; não sobrescrever sem revisão')
    descriptor, temporary = tempfile.mkstemp(prefix='read-ai-', suffix='.tmp', dir=root)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            json.dump(result, output, ensure_ascii=False, indent=2)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print(json.dumps({'published': True, 'mode': 'mock', 'cards': len(result['cards']),
                      'segments': result['segment_count'], 'database_writes': 0, 'api_calls': 0}))


if __name__ == '__main__':
    main()
