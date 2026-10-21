"""Explicit mock response: no AI calls, tasks, assignees or notifications."""
from datetime import datetime, timezone
from app.schemas.meetings import validate_extraction
from app.services.meeting_fixture import READ_AI_HASH, read_ai_example
from app.services.meeting_transcripts import digest, parse_transcript


def build_demo(raw, organization_id):
    if digest(raw) != READ_AI_HASH:
        raise ValueError('Transcrição diferente da fixture revisada; mock não publicado')
    segments, participants = parse_transcript(raw.decode('utf-8-sig'), 'read-ai-demo')
    result = validate_extraction(read_ai_example(segments), segments, participants).model_dump(mode='json')
    people = {p['id']: p['name'] for p in participants}
    cards = []
    for proposal in result['proposals']:
        cards.append({**proposal, 'speaker': people.get(proposal['owner_participant_id']),
                      'assignee_user_id': None, 'simulation': True,
                      'confirmed_date': '2026-09-24' if proposal['kind'] == 'event' else None})
    return {'schema_version': '1.0', 'organization_id': str(organization_id), 'simulation': True,
            'published_at': datetime.now(timezone.utc).isoformat(), 'source_sha256': READ_AI_HASH,
            'meeting_date': '2026-09-16', 'segment_count': len(segments),
            'title': 'Mock — transcrição READ AI', 'cards': cards,
            'notice': 'Resposta simulada determinística, não gerada por uma chamada real à IA. '
                      'Datas confirmadas pelo usuário; responsáveis internos pendentes. '
                      'Não gera tarefas operacionais, alertas ou convites.'}
