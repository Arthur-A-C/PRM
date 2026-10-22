"""Enqueue a meeting revision under an existing custodian, without publishing."""
import argparse
import uuid
from sqlalchemy.orm import Session
from app.config import get_settings
from app.db import get_engine
from app.models import User
from app.models.meetings import TranscriptRevision
from app.services.meeting_activities import get_meeting
from app.services.meeting_pipeline import enqueue, analysis_context


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--meeting',type=uuid.UUID,required=True)
    p.add_argument('--revision',type=uuid.UUID,required=True);p.add_argument('--actor',type=uuid.UUID,required=True)
    p.add_argument('--consent-to-send-text',action='store_true',required=True);args=p.parse_args()
    with Session(get_engine()) as db,db.begin():
        user=db.get(User,args.actor)
        if not user or not user.active:raise ValueError('Usuário inválido')
        meeting=get_meeting(db,user,args.meeting,lock=True);revision=db.get(TranscriptRevision,args.revision)
        if not revision or revision.meeting_id!=meeting.id or not revision.quality.get('complete'):raise ValueError('Revisão inválida/parcial; revise na aplicação')
        run=enqueue(db,meeting,'analysis',analysis_context(meeting,revision,get_settings()),revision_id=revision.id)
        print(run.id,run.state)


if __name__=='__main__':main()
