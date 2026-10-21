"""Build drafts from an already validated analysis. Never calls an AI API."""
import argparse
import json
import uuid
from sqlalchemy.orm import Session
from app.db import get_engine
from app.models import User
from app.models.meetings import MeetingRun
from app.services.meeting_activities import get_meeting
from app.services.meeting_pipeline import build_cards


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--analysis',type=uuid.UUID,required=True);p.add_argument('--actor',type=uuid.UUID,required=True);args=p.parse_args()
    with Session(get_engine()) as db,db.begin():
        user=db.get(User,args.actor);run=db.get(MeetingRun,args.analysis)
        if not user or not user.active or not run:raise ValueError('Usuário/análise inválidos')
        get_meeting(db,user,run.meeting_id)
        print(json.dumps(build_cards(db,run)))


if __name__=='__main__':main()
