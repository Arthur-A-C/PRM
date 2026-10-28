"""Single supplier scope check, reused by every read, mutation and download."""
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlsplit
from fastapi import HTTPException
from sqlalchemy import select
from app.models.identity import User
from app.models.suppliers import Supplier, SupplierInteraction
from app.services.access import MANAGERS, ROLES

STAGES = dict(zip(('base_ativa','contato_inicial','tratativa','documentacao','homologacao','negociacao','aguardando','ativo','congelado','descartado'),
                 ('Base ativa','Contato inicial','Em tratativa','Documentação / Ficha cadastral','Homologação','Negociação','Aguardando retorno','Fornecedor ativo','Congelado','Descartado')))
SCORES = {'quente':'Quente','morno':'Morno','frio':'Frio','congelando':'Congelando'}
CATEGORIES = ['Ficha cadastral','Contratos','Certidões','Tabela de preços','Catálogos','Propostas','Documentos fiscais','Dados bancários','Outros']

def active(user):
    if not user.active or user.role not in ROLES: raise HTTPException(403,'Usuário sem acesso.')

def responsible(db, actor, identifier):
    user=db.scalar(select(User).where(User.id==identifier,User.organization_id==actor.organization_id,User.active.is_(True)))
    if user is None: raise HTTPException(422,'Responsável deve ser usuário ativo da sua organização.')
    return user

def scope(db, actor, identifier, lock=False):
    active(actor)
    query=select(Supplier).where(Supplier.id==identifier,Supplier.organization_id==actor.organization_id)
    if actor.role not in MANAGERS: query=query.where(Supplier.responsible_user_id==actor.id)
    if lock: query=query.with_for_update()
    supplier=db.scalar(query)
    if supplier is None: raise HTTPException(404,'Fornecedor não encontrado ou sem acesso.')
    return supplier

def audit(db, supplier, actor, event, data=None):
    db.add(SupplierInteraction(supplier_id=supplier.id,organization_id=supplier.organization_id,
                              actor_id=actor.id,event=event,data=data or {}))

def version_check(supplier, expected):
    """updated_at is the existing optimistic lock; normalize SQLite's naive test timestamps."""
    actual=supplier.updated_at
    if actual.tzinfo is not None:actual=actual.astimezone(timezone.utc).replace(tzinfo=None)
    if expected.tzinfo is not None:expected=expected.astimezone(timezone.utc).replace(tzinfo=None)
    if actual!=expected:raise HTTPException(409,'O fornecedor foi alterado por outra pessoa. Reabra o cadastro e confirme novamente.')

def touch(supplier):
    """Make the existing updated_at lock precise and include child-record mutations."""
    supplier.updated_at=datetime.now(timezone.utc)

def row(item):
    result={'id':str(item.id),'created_at':item.created_at.isoformat(),'updated_at':item.updated_at.isoformat(),'data':item.data}
    if isinstance(item,Supplier):
        result.update(name=item.name,stage=item.stage,score=item.score,responsible_user_id=str(item.responsible_user_id),
                      archived_at=item.archived_at.isoformat() if item.archived_at else None,
                      archived_by=str(item.archived_by) if item.archived_by else None)
    else:
        result['actor_id']=str(item.actor_id)
        if hasattr(item,'event'):result['event']=item.event
        if hasattr(item,'assignee_user_id'):result['assignee_user_id']=str(item.assignee_user_id)
    return result

# --- duplicate detection (same organization; before creating a supplier) ----------------------------
LEGAL_WORDS = {'ltda','limitada','limited','ltd','co','company','cia','inc','corp','corporation','sa','s/a','me','epp','eireli',
               'gmbh','srl','spa','llc','plc','bv','ag','the','e','and','&'}
STRONG = ('cnpj','registro','dominio')

def normalized_name(value):
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().casefold()
    words = [w for w in re.split(r'[^a-z0-9]+', text) if w and w not in LEGAL_WORDS]
    name = ' '.join(words)
    return name if len(name) >= 3 else ''

def site_domain(value):
    value = str(value or '').strip()
    if not value:
        return ''
    host = (urlsplit(value if '://' in value else 'https://' + value).hostname or '').casefold().rstrip('.')
    return host[4:] if host.startswith('www.') else host

def fiscal_digits(value):
    digits = re.sub(r'\D', '', str(value or ''))
    return digits if len(digits) >= 8 else ''

def registration_key(value):
    key = re.sub(r'[\W_]', '', str(value or '')).casefold()
    return key if len(key) >= 4 else ''

def find_duplicates(db, organization_id, values):
    """values: name, legal_name, trade_name, cnpj, company_registration, website. Strong reasons first."""
    wanted = {'cnpj': fiscal_digits(values.get('cnpj')), 'registro': registration_key(values.get('company_registration')),
              'dominio': site_domain(values.get('website')),
              'nome': {n for n in (normalized_name(values.get(k)) for k in ('name', 'legal_name', 'trade_name')) if n}}
    users = {u.id: u.name for u in db.scalars(select(User).where(User.organization_id == organization_id))}
    found = []
    for s in db.scalars(select(Supplier).where(Supplier.organization_id == organization_id)):
        reasons = []
        if wanted['cnpj'] and wanted['cnpj'] == fiscal_digits(s.data.get('cnpj')): reasons.append('cnpj')
        if wanted['registro'] and wanted['registro'] in {registration_key(s.data.get('company_registration')), registration_key(s.data.get('cnpj'))}: reasons.append('registro')
        if wanted['dominio'] and wanted['dominio'] == site_domain(s.data.get('website')): reasons.append('dominio')
        names = {n for n in (normalized_name(v) for v in (s.name, s.data.get('legal_name'), s.data.get('trade_name'))) if n}
        if wanted['nome'] & names: reasons.append('nome')
        if reasons:
            found.append({'id': str(s.id), 'name': s.name, 'responsible': users.get(s.responsible_user_id, ''), 'stage': STAGES.get(s.stage, s.stage),
                          'reasons': reasons, 'strong': any(r in STRONG for r in reasons),
                          'created_at': s.created_at.isoformat() if s.created_at else None})
    return sorted(found, key=lambda d: (not d['strong'], d['name'].casefold()))
