"""Audit/migrate/seed meeting module. Explicit target; never publishes example tasks."""
import argparse
import importlib.util
import json
import uuid
from datetime import date
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text, inspect, func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.config import get_settings
from app.models import Organization, User
from app.models.meetings import Meeting, Activity, MeetingRun
from app.schemas.meetings import Extraction, validate_extraction
from app.services.meeting_transcripts import digest
from app.services.meeting_pipeline import add_revision, analysis_context, enqueue, build_cards
from app.services.meeting_fixture import READ_AI_HASH, read_ai_example


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['inspect','migrate','seed-example','schema'])
    parser.add_argument('--target',choices=['staging','production'],default='staging')
    parser.add_argument('--transcript',type=Path)
    parser.add_argument('--actor',type=uuid.UUID)
    args=parser.parse_args();settings=get_settings()
    if args.action=='schema':
        folder=Path('config/meetings');folder.mkdir(parents=True,exist_ok=True)
        (folder/'extraction.schema.json').write_text(json.dumps(Extraction.model_json_schema(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('Generated extraction.schema.json');return
    url=make_url(settings.database_url).set(database='prm_pipeline_staging' if args.target=='staging' else 'prm_mvp')
    engine=create_engine(url)
    if args.action=='inspect':
        with engine.connect() as conn:
            conn.execute(text('SET TRANSACTION READ ONLY'))
            print(json.dumps({'database':url.database,'migration':conn.execute(text('select version_num from alembic_version')).scalars().all(),
                'tables':[t for t in inspect(conn).get_table_names() if t in ['meetings','activities']],
                'active_roles':[list(row) for row in conn.execute(select(User.role,func.count()).where(User.active.is_(True)).group_by(User.role))],
                'asr_installed':importlib.util.find_spec('faster_whisper') is not None,'meeting_model_configured':bool(settings.meeting_ai_model)},default=str))
        return
    if args.action=='migrate':
        with engine.begin() as conn:
            config=Config('alembic.ini');config.attributes['connection']=conn
            command.upgrade(config,'20261016_0009')
        print('Migrated additive tables:',url.database);return
    if not args.transcript:
        parser.error('--transcript is required')
    raw=args.transcript.read_bytes()
    if digest(raw)!=READ_AI_HASH:raise ValueError('Fixture READ AI diferente; não aplicar propostas pré-definidas')
    with Session(engine) as db,db.begin():
        org=db.scalar(select(Organization).where(Organization.name==settings.organization_name))
        if not org:raise ValueError('Organização configurada não encontrada')
        # No invented account. A custodian must explicitly exist; without an actor require unique manager.
        users=list(db.scalars(select(User).where(User.organization_id==org.id,User.active.is_(True),User.role.in_(['gestor','desenvolvedor']))))
        actor=next((u for u in users if u.id==args.actor),None) if args.actor else users[0] if len(users)==1 else None
        if not actor:raise ValueError('Informe --actor UUID de gestor existente; nenhuma conta será criada')
        key='[EXEMPLO READ AI] E-commerce e integrações · 16/09/2026'
        meeting=db.scalar(select(Meeting).where(Meeting.organization_id==org.id,Meeting.title==key))
        if meeting:
            print(json.dumps({'meeting_id':str(meeting.id),'status':'already_exists','published':False}));return
        meeting=Meeting(organization_id=org.id,creator_id=actor.id,title=key,partner='Fornecedor a confirmar',
                        meeting_date=date(2026,9,16),timezone='America/Sao_Paulo',version=1,participants=[],
                        metadata_confirmed={'event_date':'2026-09-24','origin':'human','reason':'Datas confirmadas pelo operador na conversa em 16/10/2026; responsáveis pendentes'})
        db.add(meeting);db.flush()
        revision=add_revision(db,meeting,actor.id,raw.decode('utf-8-sig'),'txt',{'complete':True,'original_bytes_sha256':digest(raw)})
        run=enqueue(db,meeting,'analysis',analysis_context(meeting,revision,settings,'fixture'),revision_id=revision.id)
        result=validate_extraction(read_ai_example(revision.segments),revision.segments,meeting.participants).model_dump(mode='json')
        run.raw_output,run.result,run.state=result,result,'succeeded';db.flush()
        built=build_cards(db,run)
        for item in db.scalars(select(Activity).where(Activity.meeting_id==meeting.id,Activity.kind=='event')):
            item.due_date=date(2026,9,24)
            item.details={**item.details,'date_origin':'human','date_reason':'Data confirmada pelo operador; 15h continua candidata'}
        print(json.dumps({'meeting_id':str(meeting.id),'cards':built,'published':False,'simulation':True}))


if __name__=='__main__':main()
