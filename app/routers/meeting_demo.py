import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Response
from app.dependencies import CurrentAuth, AppSettings

router = APIRouter(prefix='/api/v1/meeting-demo', tags=['demonstração de reuniões'])


@router.get('')
def demo(auth: CurrentAuth, settings: AppSettings, response: Response):
    response.headers['Cache-Control'] = 'private, no-store'
    # Same scope as reviewing a meeting: managers in the owning organization.
    if auth.user.role not in {'gestor', 'desenvolvedor'}:
        raise HTTPException(403, 'Demonstração disponível para gestores autorizados')
    path = Path(settings.meeting_storage_dir) / 'read-ai-dashboard-demo.json'
    if not path.is_file():
        return {'available': False}
    content = json.loads(path.read_text(encoding='utf-8'))
    if content.get('organization_id') != str(auth.user.organization_id):
        return {'available': False}
    return {'available': True, **{k: v for k, v in content.items() if k != 'organization_id'}}
