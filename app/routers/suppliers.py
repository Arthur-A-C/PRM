import hashlib
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from app.dependencies import CurrentAuth, DbSession, AppSettings
from app.models.identity import User
from app.models.suppliers import Supplier, SupplierContact, SupplierTask, SupplierDocument, SupplierInteraction
from app.services import suppliers as service
from app.services.access import MANAGERS
from app.services.security import secrets_match

def guard(auth: CurrentAuth, csrf: Annotated[str|None,Header(alias='X-CSRF-Token')]=None):
    service.active(auth.user)
    if not csrf or not secrets_match(auth.login_session.csrf_hash,csrf): raise HTTPException(403,'CSRF inválido.')

router=APIRouter(prefix='/api/v1/fornecedores',tags=['Fornecedores'])
WRITE=[Depends(guard)]

class Fields(BaseModel):
    model_config=ConfigDict(extra='forbid',str_max_length=4000)

class SupplierInput(Fields):
    name: str=Field(min_length=1,max_length=200)
    responsible_user_id: uuid.UUID|None=None
    stage: str='base_ativa'
    score: str='morno'
    legal_name: str=''
    trade_name: str=''
    cnpj: str=Field(default='',max_length=30)
    state_registration: str=''
    address: str=''
    number: str=''
    complement: str=''
    neighborhood: str=''
    city: str=''
    uf: str=Field(default='',max_length=2)
    cep: str=''
    website: str=''
    phone: str=''
    email: str=''
    segment: str=''
    category: str=''
    payment_terms: str=''
    average_lead_time: str=''
    carrier: str=''
    notes: str=''
    next_action: str=''
    next_action_date: date|None=None
    primary_contact: str=''
    # Cadastro internacional / preenchimento com IA (opcionais; fornecedor antigo continua válido).
    country: str=''
    company_registration: str=''
    province: str=''
    mobile: str=''
    whatsapp: str=''
    email_commercial: str=''
    email_financial: str=''
    products: str=''
    currency: str=''
    social_links: str=''

class ContactInput(Fields):
    name: str=Field(min_length=1,max_length=200)
    role: str=''
    type: Literal['Comercial','Financeiro','Fiscal','Suporte','Logística','Diretoria','Outro']='Comercial'
    email: str=''
    phone: str=''
    whatsapp: str=''
    is_primary: bool=False
    notes: str=''

class InteractionInput(Fields):
    type: Literal['Ligação','E-mail','WhatsApp','Reunião','Interno','Documento recebido','Documento enviado','Negociação','Outro']='Interno'
    summary: str=Field(min_length=1,max_length=500)
    description: str=''
    next_step: str=''

class TaskInput(Fields):
    title: str=Field(min_length=1,max_length=300)
    description: str=''
    assignee_user_id: uuid.UUID|None=None
    due_date: date|None=None
    priority: Literal['baixa','normal','alta']='normal'
    status: Literal['pendente','concluida']='pendente'

class DocumentInput(Fields):
    category: str='Outros'
    description: str=''
    status: Literal['Vigente','Vencido','Substituído','Em revisão']='Em revisão'
    valid_until: date|None=None
    start_date: date|None=None
    version: str=''

def validate_supplier(db,user,body):
    if not body.name.strip(): raise HTTPException(422,'Informe nome da empresa.')
    if body.stage not in service.STAGES or body.score not in service.SCORES: raise HTTPException(422,'Etapa/score inválido.')
    identifier=body.responsible_user_id or user.id
    if user.role not in MANAGERS and identifier!=user.id: raise HTTPException(403,'Você pode atribuir apenas a si mesmo.')
    service.responsible(db,user,identifier)
    return identifier

@router.get('/config')
def config(db:DbSession,auth:CurrentAuth):
    service.active(auth.user)
    users=db.scalars(select(User).where(User.organization_id==auth.user.organization_id,User.active.is_(True)).order_by(User.name)).all()
    return {'stages':service.STAGES,'scores':service.SCORES,'categories':service.CATEGORIES,'user_id':str(auth.user.id),
            'manager':auth.user.role in MANAGERS,'users':[{'id':str(u.id),'name':u.name} for u in users]}

@router.get('')
def listing(db:DbSession,auth:CurrentAuth,q:str='',responsible_user_id:uuid.UUID|None=None,stage:str='',score:str='',category:str='',city:str='',uf:str=''):
    service.active(auth.user)
    query=select(Supplier).where(Supplier.organization_id==auth.user.organization_id).order_by(Supplier.updated_at.desc())
    if auth.user.role not in MANAGERS:query=query.where(Supplier.responsible_user_id==auth.user.id)
    if responsible_user_id:query=query.where(Supplier.responsible_user_id==responsible_user_id)
    if stage:query=query.where(Supplier.stage==stage)
    if score:query=query.where(Supplier.score==score)
    items=[s for s in db.scalars(query) if (not q or q.casefold() in (s.name+' '+s.data.get('cnpj','')).casefold())
           and (not category or category.casefold() in (s.data.get('category','')+' '+s.data.get('segment','')).casefold())
           and (not city or city.casefold() in s.data.get('city','').casefold()) and (not uf or uf.casefold()==s.data.get('uf','').casefold())]
    rows=[service.row(s) for s in items]
    # Internal supplier tasks only: no Planner/Activity writes or automatic alerts.
    pending=db.scalars(select(SupplierTask).where(SupplierTask.organization_id==auth.user.organization_id,
        SupplierTask.supplier_id.in_([s.id for s in items]))).all() if items else []
    for row in rows:
        tasks=sorted((t for t in pending if str(t.supplier_id)==row['id'] and t.data.get('status')=='pendente'),key=lambda t:t.data.get('due_date') or '9999')
        if tasks and not row['data'].get('next_action'):
            row['data']={**row['data'],'next_action':tasks[0].data['title'],'next_action_date':tasks[0].data.get('due_date')}
    return {'items':rows,'columns':{k:[str(s.id) for s in items if s.stage==k] for k in service.STAGES}}

@router.post('',dependencies=WRITE)
def create(body:SupplierInput,db:DbSession,auth:CurrentAuth):
    owner=validate_supplier(db,auth.user,body)
    supplier=Supplier(organization_id=auth.user.organization_id,responsible_user_id=owner,name=body.name.strip(),stage=body.stage,score=body.score,
                      data=body.model_dump(mode='json',exclude={'name','stage','score','responsible_user_id'}))
    db.add(supplier);db.flush()
    if body.primary_contact:
        db.add(SupplierContact(supplier_id=supplier.id,organization_id=supplier.organization_id,actor_id=auth.user.id,
            data=ContactInput(name=body.primary_contact,is_primary=True).model_dump()))
    service.audit(db,supplier,auth.user,'supplier_created',{'name':supplier.name});db.commit();db.refresh(supplier)
    return service.row(supplier)

@router.get('/{identifier}')
def detail(identifier:uuid.UUID,db:DbSession,auth:CurrentAuth):
    supplier=service.scope(db,auth.user,identifier)
    result=service.row(supplier)
    for key,model in [('contacts',SupplierContact),('tasks',SupplierTask),('documents',SupplierDocument),('history',SupplierInteraction)]:
        result[key]=[service.row(x) for x in db.scalars(select(model).where(model.supplier_id==identifier,model.organization_id==auth.user.organization_id).order_by(model.created_at.desc()))]
    return result

@router.put('/{identifier}',dependencies=WRITE)
def update(identifier:uuid.UUID,body:SupplierInput,db:DbSession,auth:CurrentAuth):
    s=service.scope(db,auth.user,identifier,True);owner=validate_supplier(db,auth.user,body)
    for key,new,event in [('stage',body.stage,'stage_changed'),('score',body.score,'score_changed'),('responsible_user_id',owner,'responsible_changed')]:
        old=getattr(s,key)
        if old!=new:service.audit(db,s,auth.user,event,{'before':str(old),'after':str(new)})
        setattr(s,key,new)
    data=body.model_dump(mode='json',exclude={'name','stage','score','responsible_user_id'})
    if any(s.data.get(k)!=data.get(k) for k in ('next_action','next_action_date')):service.audit(db,s,auth.user,'next_action_changed',{'title':body.next_action,'due_date':data['next_action_date']})
    if s.data.get('last_interaction'):data['last_interaction']=s.data['last_interaction']
    s.name=body.name.strip();s.data=data;service.audit(db,s,auth.user,'supplier_updated');db.commit();return service.row(s)

class QuickUpdate(Fields):
    stage: str|None=None
    expected_stage: str|None=None
    score: str|None=None
    responsible_user_id: uuid.UUID|None=None
    next_action: str|None=None
    next_action_date: date|None=None

@router.patch('/{identifier}',dependencies=WRITE)
def quick_update(identifier:uuid.UUID,body:QuickUpdate,db:DbSession,auth:CurrentAuth):
    s=service.scope(db,auth.user,identifier,True)
    if body.expected_stage is not None and body.expected_stage!=s.stage:
        raise HTTPException(409,'A etapa foi alterada por outra pessoa. Atualize e tente novamente.')
    if 'stage' in body.model_fields_set and body.stage not in service.STAGES:raise HTTPException(422,'Etapa inválida.')
    if 'score' in body.model_fields_set and body.score not in service.SCORES:raise HTTPException(422,'Score inválido.')
    if 'responsible_user_id' in body.model_fields_set:
        if body.responsible_user_id is None:raise HTTPException(422,'Responsável obrigatório.')
        if auth.user.role not in MANAGERS and body.responsible_user_id!=auth.user.id:raise HTTPException(403,'Você pode atribuir apenas a si mesmo.')
        service.responsible(db,auth.user,body.responsible_user_id)
    for key,event in [('stage','stage_changed'),('score','score_changed'),('responsible_user_id','responsible_changed')]:
        if key in body.model_fields_set and getattr(s,key)!=getattr(body,key):
            service.audit(db,s,auth.user,event,{'before':str(getattr(s,key)),'after':str(getattr(body,key))})
            setattr(s,key,getattr(body,key))
    changed={k:v for k,v in body.model_dump(mode='json',exclude_unset=True).items() if k in {'next_action','next_action_date'}}
    if changed:
        if changed.get('next_action') is None and 'next_action' in changed:changed['next_action']=''
        s.data={**s.data,**changed};service.audit(db,s,auth.user,'next_action_changed',changed)
    db.commit();return service.row(s)

def child(db,user,supplier,model,identifier):
    obj=db.scalar(select(model).where(model.id==identifier,model.supplier_id==supplier.id,model.organization_id==user.organization_id))
    if obj is None:raise HTTPException(404,'Registro não encontrado.')
    return obj

@router.post('/{identifier}/contacts',dependencies=WRITE)
@router.put('/{identifier}/contacts/{contact_id}',dependencies=WRITE)
def contact(identifier:uuid.UUID,body:ContactInput,db:DbSession,auth:CurrentAuth,contact_id:uuid.UUID|None=None):
    s=service.scope(db,auth.user,identifier,True)
    if body.is_primary:
        for c in db.scalars(select(SupplierContact).where(SupplierContact.supplier_id==s.id,SupplierContact.organization_id==s.organization_id)):
            c.data={**c.data,'is_primary':False}
    c=child(db,auth.user,s,SupplierContact,contact_id) if contact_id else SupplierContact(supplier_id=s.id,organization_id=s.organization_id,actor_id=auth.user.id)
    c.data=body.model_dump();db.add(c);service.audit(db,s,auth.user,'contact_updated' if contact_id else 'contact_created',{'name':body.name});db.commit();return service.row(c)

@router.post('/{identifier}/interactions',dependencies=WRITE)
def interaction(identifier:uuid.UUID,body:InteractionInput,db:DbSession,auth:CurrentAuth):
    s=service.scope(db,auth.user,identifier,True);service.audit(db,s,auth.user,'interaction_created',body.model_dump())
    s.data={**s.data,'last_interaction':datetime.now(timezone.utc).isoformat()};db.commit();return {'ok':True}

@router.post('/{identifier}/tasks',dependencies=WRITE)
@router.put('/{identifier}/tasks/{task_id}',dependencies=WRITE)
def task(identifier:uuid.UUID,body:TaskInput,db:DbSession,auth:CurrentAuth,task_id:uuid.UUID|None=None):
    s=service.scope(db,auth.user,identifier,True);owner=body.assignee_user_id or auth.user.id
    service.responsible(db,auth.user,owner)
    t=child(db,auth.user,s,SupplierTask,task_id) if task_id else SupplierTask(supplier_id=s.id,organization_id=s.organization_id,actor_id=auth.user.id)
    completed=(t.data or {}).get('completed_at') if (t.data or {}).get('status')=='concluida' else None
    t.assignee_user_id=owner;t.data=body.model_dump(mode='json',exclude={'assignee_user_id'})
    t.data['completed_at']=(completed or datetime.now(timezone.utc).isoformat()) if body.status=='concluida' else None
    db.add(t);service.audit(db,s,auth.user,'task_completed' if body.status=='concluida' else 'task_updated' if task_id else 'task_created',{'title':body.title});db.commit();return service.row(t)

def storage(settings):
    root=Path(settings.supplier_storage_dir).resolve();root.mkdir(parents=True,exist_ok=True);return root

def document_path(settings,user,identifier,doc_id):
    return storage(settings)/str(user.organization_id)/str(identifier)/str(doc_id)

MIMES={'.pdf':'application/pdf','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg',
       '.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
       '.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.csv':'text/csv','.txt':'text/plain',
       '.xls':'application/vnd.ms-excel'}
OLE=b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'

def save_upload(file,path):
    """Validated streaming write (name, extension, signature, 20 MiB, SHA-256). Removes the file on any error.
    Shared by document upload and by the ficha of a supplier still being created with AI."""
    name=file.filename or ''
    if len(name)>200 or any(ord(c)<32 for c in name) or any(c in name for c in ('/','\\')) or name in {'.','..'}:raise HTTPException(422,'Nome de arquivo inválido.')
    suffix=Path(name).suffix.lower()
    if suffix not in MIMES:raise HTTPException(422,'Formato não permitido. Use PDF, PNG, JPG, XLSX, XLS, DOCX, CSV ou TXT.')
    path.parent.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256();size=0;head=b''
    try:
        with path.open('xb') as out:
            while chunk:=file.file.read(1024*1024):
                size+=len(chunk)
                if size>20*1024**2:raise HTTPException(413,'Documento acima de 20 MiB.')
                if not head:head=chunk[:1024]
                digest.update(chunk);out.write(chunk)
        from app.services.local_uploads import signature_ok
        valid=head.startswith(OLE) if suffix=='.xls' else signature_ok('.zip' if suffix in {'.xlsx','.docx'} else '.csv' if suffix=='.txt' else suffix,head)
        if not size or not valid:raise HTTPException(422,'Conteúdo não corresponde ao formato.')
    except BaseException:
        path.unlink(missing_ok=True);raise
    finally:file.file.close()
    return {'original_name':name,'mime':MIMES[suffix],'size':size,'sha256':digest.hexdigest()}

@router.post('/{identifier}/documents',dependencies=WRITE)
def document(identifier:uuid.UUID,db:DbSession,auth:CurrentAuth,settings:AppSettings,
             file:Annotated[UploadFile,File()],category:Annotated[str,Form()]='Outros',description:Annotated[str,Form(max_length=4000)]=''):
    s=service.scope(db,auth.user,identifier,True)
    if category not in service.CATEGORIES:raise HTTPException(422,'Categoria inválida.')
    doc_id=uuid.uuid4();path=document_path(settings,auth.user,identifier,doc_id)
    meta=save_upload(file,path)
    try:
        doc=SupplierDocument(id=doc_id,supplier_id=s.id,organization_id=s.organization_id,actor_id=auth.user.id,
            data={**meta,'category':category,'description':description,'status':'Em revisão','valid_until':None,'start_date':None,'version':''})
        db.add(doc);service.audit(db,s,auth.user,'document_uploaded',{'name':meta['original_name'],'category':category});db.commit();return service.row(doc)
    except BaseException:
        db.rollback();path.unlink(missing_ok=True);raise

@router.put('/{identifier}/documents/{document_id}',dependencies=WRITE)
def organize(identifier:uuid.UUID,document_id:uuid.UUID,body:DocumentInput,db:DbSession,auth:CurrentAuth):
    s=service.scope(db,auth.user,identifier,True);doc=child(db,auth.user,s,SupplierDocument,document_id)
    if body.category not in service.CATEGORIES:raise HTTPException(422,'Categoria inválida.')
    doc.data={**doc.data,**body.model_dump(mode='json')};service.audit(db,s,auth.user,'document_updated',{'document_id':str(doc.id)});db.commit();return service.row(doc)

@router.get('/{identifier}/documents/{document_id}/download')
def download(identifier:uuid.UUID,document_id:uuid.UUID,db:DbSession,auth:CurrentAuth,settings:AppSettings):
    s=service.scope(db,auth.user,identifier);doc=child(db,auth.user,s,SupplierDocument,document_id)
    path=document_path(settings,auth.user,identifier,document_id)
    if not path.is_file():raise HTTPException(404,'Arquivo indisponível.')
    return FileResponse(path,media_type=doc.data['mime'],filename=doc.data['original_name'],headers={'X-Content-Type-Options':'nosniff','Cache-Control':'no-store'})
