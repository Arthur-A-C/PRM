"""Read-only PostgreSQL/API smoke; never publishes cards or calls an AI provider."""
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text, func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db_session
from app.dependencies import get_current_auth
from app.main import app
from app.models import User
from app.models.meetings import Meeting, Activity, ActivityAlert


def main():
    url = make_url(get_settings().database_url).set(database='prm_pipeline_staging')
    engine = create_engine(url)
    with Session(engine) as db:
        db.execute(text('SET TRANSACTION READ ONLY'))
        meeting = db.scalar(select(Meeting).where(Meeting.title.like('[EXEMPLO READ AI]%')))
        if not meeting:
            raise RuntimeError('Execute seed-example em staging primeiro')
        actor = db.get(User, meeting.creator_id)
        app.dependency_overrides[get_db_session] = lambda: db
        app.dependency_overrides[get_current_auth] = lambda: SimpleNamespace(user=actor)
        try:
            with TestClient(app) as client:
                paths = ['/users', '/meetings', f'/meetings/{meeting.id}',
                         '/activities', '/activities/overview', '/alerts',
                         '/activities/calendar?start=2026-09-01&end=2026-10-01',
                         '/activities/calendar?start=2026-09-01&end=2026-10-01&include_proposals=true']
                responses = [client.get('/api/v1/planner' + path) for path in paths]
                assert all(response.status_code == 200 for response in responses)
                assert len(responses[-2].json()['items']) == 0
                assert len(responses[-1].json()['items']) == 1
                assert responses[-1].json()['items'][0]['calendar_date'] == '2026-09-24'
                assert responses[4].json()['denominator'] == 0
                rows = db.scalars(select(Activity).where(Activity.meeting_id == meeting.id)).all()
                assert len(rows) == 7 and all(a.approval == 'draft' and not a.assignee_user_id for a in rows)
                assert db.scalar(select(func.count()).select_from(ActivityAlert).where(ActivityAlert.activity_id.in_([a.id for a in rows]))) == 0
                print(json.dumps({'database': url.database, 'routes_ok': len(paths), 'drafts': len(rows),
                                  'assigned': 0, 'published': 0, 'alerts': 0,
                                  'meeting_date': str(meeting.meeting_date), 'event_date': '2026-09-24'}))
        finally:
            app.dependency_overrides.clear()
            db.rollback()
    engine.dispose()


if __name__ == '__main__':
    main()
