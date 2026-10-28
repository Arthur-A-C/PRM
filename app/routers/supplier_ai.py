"""Preencher fornecedor com IA (existing supplier) and Novo fornecedor com IA (supplier created only after review).
analisar-* only return a PREVIEW (plus an audit run); only aplicar/criar write, and only reviewed choices validated
against the server-stored preview. Same scope/CSRF rules as the supplier module."""
import os
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Literal
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import Field, ValidationError
from sqlalchemy import select, text
from app.dependencies import CurrentAuth, DbSession, AppSettings
from app.models.suppliers import Supplier, SupplierAIRun, SupplierContact, SupplierDocument
from app.routers import suppliers as routes
from app.services import supplier_ai as ai, supplier_web as web, suppliers as service

router=APIRouter(prefix='/api/v1/fornecedores',tags=['Fornecedores IA'])
READABLE={'.pdf','.docx','.xlsx','.xls','.csv','.txt','.png','.jpg','.jpeg'}
FAILED='Não foi possível analisar esta fonte. Nenhum dado foi alterado.'

class SiteInput(routes.Fields):
    url: str=Field(default='',max_length=500)

class DocumentInput(routes.Fields):
    document_id: uuid.UUID
    url: str=Field(default='',max_length=500)

class Choice(routes.Fields):
    key: str
    choice: int=Field(ge=0,le=50)
    action: Literal['replace','append','contact']='replace'

class ApplyInput(routes.Fields):
    run_id: uuid.UUID
    fields: list[Choice]=Field(default_factory=list,max_length=60)
    contacts: list[str]=Field(default_factory=list,max_length=100)
    social: list[str]=Field(default_factory=list,max_length=50)

def contacts_of(db,supplier):
    return db.scalars(select(SupplierContact).where(SupplierContact.supplier_id==supplier.id,SupplierContact.organization_id==supplier.organization_id)).all()

def aware(moment):
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment

def rate_limit(db,user,settings):
    recent=db.scalars(select(SupplierAIRun.created_at).where(SupplierAIRun.actor_id==user.id,SupplierAIRun.organization_id==user.organization_id)
                      .order_by(SupplierAIRun.created_at.desc()).limit(settings.supplier_ai_max_runs_per_hour)).all()
    now=datetime.now(timezone.utc)
    if len(recent)>=settings.supplier_ai_max_runs_per_hour and all((now-aware(t)).total_seconds()<3600 for t in recent):
        raise HTTPException(429,'Limite de análises com IA por hora atingido. Tente novamente mais tarde.')

def cached(db,organization_id,supplier_id,actor,digest,model,settings):
    """Same supplier (or, before it exists, same person) + same collected content + same model."""
    if not settings.supplier_ai_cache_minutes:return None
    owner=SupplierAIRun.supplier_id==supplier_id if supplier_id else (SupplierAIRun.supplier_id.is_(None)&(SupplierAIRun.actor_id==actor.id))
    run=db.scalar(select(SupplierAIRun).where(owner,SupplierAIRun.organization_id==organization_id,
        SupplierAIRun.source_hash==digest,SupplierAIRun.model==model,SupplierAIRun.status.in_(('ok','applied'))).order_by(SupplierAIRun.created_at.desc()).limit(1))
    if run and (datetime.now(timezone.utc)-aware(run.created_at)).total_seconds()<settings.supplier_ai_cache_minutes*60:return run
    return None

def hints_of(pages):
    """Deterministic findings handed to the model (already literal in the sources)."""
    return {'emails':sorted({e for p in pages for e in p.emails})[:30],'telefones':sorted({t for p in pages for t in p.phones})[:30],
            'whatsapp':sorted({'+'+w for p in pages for w in p.whatsapp})[:10],'redes_sociais':sorted({u for p in pages for _,u in p.social})[:20],
            'meta':{k:v for p in pages[:1] for k,v in p.meta.items()}}

def ready(db,user,settings):
    if not ai.enabled(settings):raise HTTPException(503,'IA de fornecedores não configurada no servidor. Nenhum dado foi alterado.')
    rate_limit(db,user,settings)

def analyze(db,auth,settings,identifier,url=None,document_id=None,site=False):
    s=service.scope(db,auth.user,identifier)
    ready(db,auth.user,settings)
    snap=ai.snapshot(s,contacts_of(db,s))
    source={'type':'combined' if document_id and site else 'supplier_document' if document_id else 'website'}
    doc=path=None;suffix=''
    if document_id:
        doc=routes.child(db,auth.user,s,SupplierDocument,document_id);suffix=Path(doc.data.get('original_name','')).suffix.lower()
        if suffix not in READABLE:raise HTTPException(422,'Formato não suportado para leitura com IA.')
        path=routes.document_path(settings,auth.user,identifier,doc.id)
        if not path.is_file():raise HTTPException(404,'Arquivo indisponível.')
        source.update(document_id=str(doc.id),document_name=doc.data.get('original_name',''),category=doc.data.get('category',''))
    website=(url or '').strip() or s.data.get('website','')
    if site and not website:raise HTTPException(422,'Informe o site oficial do fornecedor.')
    return ai.preview(run_analysis(db,auth.user,settings,organization_id=s.organization_id,supplier_id=s.id,snap=snap,source=source,
                                   doc=doc,path=path,suffix=suffix,website=website,site=site))

def run_analysis(db,user,settings,*,organization_id,supplier_id,snap,source,doc=None,path=None,suffix='',website='',site=False,extra=None):
    """Shared analysis core: sources → deterministic findings → model (or cache) → grounded suggestions → run.
    Works with supplier_id=None (new supplier): nothing here writes to suppliers."""
    org=organization_id
    db.commit()  # ends the read transaction: no row lock/transaction held during network and AI calls
    sources,images,warnings,pages,site_pages=[],[],[],[],[]
    try:
        if doc is not None:
            found,images=ai.document_sources(path,suffix,doc,settings)
            warnings+=[x['warning'] for x in found if x.get('warning')];sources+=[x for x in found if x.get('text')]
            if len(images)>settings.supplier_ai_max_images:images=images[:settings.supplier_ai_max_images];warnings.append('Somente as primeiras páginas digitalizadas foram enviadas.')
        if site:
            collected=web.crawl(website,settings,transport=web.make_transport())
            found,site_pages=ai.site_sources(collected,settings.supplier_ai_page_text_chars)
            sources+=found;warnings+=collected.warnings;pages=[p.url for p in collected.pages]
            source.update(url=collected.start_url,domain=collected.base)
    except web.Blocked as exc:raise HTTPException(422,f'{exc} Nenhum dado foi alterado.') from None
    except web.FetchError as exc:raise HTTPException(502,f'{exc} Nenhum dado foi alterado.') from None
    except (ValueError,KeyError,OSError,zipfile.BadZipFile,RuntimeError) as exc:
        ai.log.warning('supplier_ai document read failed: %s',type(exc).__name__)
        raise HTTPException(422,'Não foi possível ler o documento. Nenhum dado foi alterado.') from None
    sources,dropped=ai.budget(sources,settings.supplier_ai_max_input_chars)
    if dropped:warnings.append(f'{dropped} página(s)/trecho(s) não enviados à IA por limite de tamanho.')
    if not sources and not images:raise HTTPException(422,'Nenhum conteúdo legível encontrado na fonte. Nenhum dado foi alterado.')
    model=settings.supplier_ai_model.strip();digest=ai.source_hash(model,sources,images)
    base=dict(organization_id=org,supplier_id=supplier_id,actor_id=user.id,source_type=source['type'],source_hash=digest,model=model)
    reuse=cached(db,org,supplier_id,user,digest,model,settings)
    collector=ai.Collector(sources,images);ai.deterministic(collector,site_pages,sources)
    if reuse:
        extraction,usage=reuse.data['extraction'],{}
    else:
        try:
            extraction,usage=ai.call_model(settings,sources,images,hints_of(site_pages),client=ai.make_client(settings))
        except (ai.AIFailure,ai.NotConfigured) as exc:
            db.add(SupplierAIRun(**base,status='failed',data={'source':source,'error':str(exc),'diagnostic':getattr(exc,'diagnostic',None),'prompt_version':ai.PROMPT_VERSION,'pages':pages,**(extra or {})}));db.commit()
            raise HTTPException(502,f'{FAILED} {exc}') from None
    ai.normalize(extraction,collector)
    run=SupplierAIRun(**base,status='ok',data={'source':source,'snapshot':snap,'extraction':extraction,'result':ai.extraction_result(collector),
        'warnings':warnings,'pages':pages,'usage':usage,'cached_from':str(reuse.id) if reuse else None,'prompt_version':ai.PROMPT_VERSION,
        'sent':{'sources':len(sources),'images':len(images),'chars':sum(len(x['text']) for x in sources)},**(extra or {})})
    db.add(run);db.commit();db.refresh(run)
    return run

@router.get('/{identifier}/ai/status')
def status(identifier:uuid.UUID,db:DbSession,auth:CurrentAuth,settings:AppSettings):
    service.scope(db,auth.user,identifier)
    return {'enabled':ai.enabled(settings),'readable':sorted(READABLE),'max_pages':settings.supplier_ai_max_pages}

@router.post('/{identifier}/ai/analisar-site',dependencies=routes.WRITE)
def analyze_site(identifier:uuid.UUID,body:SiteInput,db:DbSession,auth:CurrentAuth,settings:AppSettings):
    return analyze(db,auth,settings,identifier,url=body.url,site=True)

@router.post('/{identifier}/ai/analisar-documento',dependencies=routes.WRITE)
def analyze_document(identifier:uuid.UUID,body:DocumentInput,db:DbSession,auth:CurrentAuth,settings:AppSettings):
    return analyze(db,auth,settings,identifier,document_id=body.document_id)

@router.post('/{identifier}/ai/analisar-combinado',dependencies=routes.WRITE)
def analyze_combined(identifier:uuid.UUID,body:DocumentInput,db:DbSession,auth:CurrentAuth,settings:AppSettings):
    return analyze(db,auth,settings,identifier,url=body.url,document_id=body.document_id,site=True)

@router.get('/{identifier}/ai/execucoes/{run_id}')
def get_run(identifier:uuid.UUID,run_id:uuid.UUID,db:DbSession,auth:CurrentAuth):
    s=service.scope(db,auth.user,identifier);run=routes.child(db,auth.user,s,SupplierAIRun,run_id)
    if run.status not in ('ok','applied'):raise HTTPException(404,'Análise indisponível.')
    return ai.preview(run)

@router.post('/{identifier}/ai/aplicar',dependencies=routes.WRITE)
def apply(identifier:uuid.UUID,body:ApplyInput,db:DbSession,auth:CurrentAuth):
    s=service.scope(db,auth.user,identifier,True);run=routes.child(db,auth.user,s,SupplierAIRun,body.run_id)
    if run.status!='ok':raise HTTPException(409,'Esta análise já foi aplicada ou não está disponível. Faça uma nova análise.')
    if ai.expired(run):raise HTTPException(409,'Análise expirada. Faça uma nova análise.')
    preview=ai.preview(run);by_key={f['key']:f for f in preview['fields']};before=run.data['snapshot']
    now=ai.snapshot(s,contacts_of(db,s));label=ai.source_label(run.data['source'])
    if len({c.key for c in body.fields})!=len(body.fields):raise HTTPException(422,'Campo repetido na seleção.')
    data,applied,changed,new_contacts,skipped=dict(s.data),[],[],[],[]
    for choice in body.fields:
        field=by_key.get(choice.key)
        if field is None or choice.choice>=len(field['suggestions']) or choice.action not in field['actions']:raise HTTPException(422,'Seleção inválida.')
        if now['data'].get(choice.key,'')!=before['data'].get(choice.key,''):changed.append(field['label']);continue
        suggestion=field['suggestions'][choice.choice];value=suggestion['value']
        if choice.action=='replace':data[choice.key]=value
        elif choice.action=='append':data[choice.key]=(str(data.get(choice.key) or '').rstrip()+'\n'+value).strip()
        else:
            contact={'name':field['label'],'role':'','department':'','email':value if field['kind']=='email' else '',
                     'phone':value if choice.key=='phone' else '','mobile':value if choice.key=='mobile' else '','whatsapp':value if choice.key=='whatsapp' else ''}
            if ai.duplicate_contact(contact,now['contacts']):skipped.append(value);continue
            new_contacts.append(ai.contact_payload(contact,label))
        applied.append({'key':choice.key,'label':field['label'],'action':choice.action,'value':value,
                        **{k:suggestion[k] for k in ('source_type','source','document_id','page','confidence') if k in suggestion}})
    if changed:
        db.rollback()
        raise HTTPException(409,'A ficha foi alterada desde a análise ('+', '.join(changed)+'). Nada foi aplicado; revise e analise novamente.')
    contacts={c['id']:c for c in preview['contacts']}
    if len(set(body.contacts))!=len(body.contacts) or any(c not in contacts for c in body.contacts):raise HTTPException(422,'Contato inválido.')
    for cid in body.contacts:
        if ai.duplicate_contact(contacts[cid],now['contacts']):skipped.append(contacts[cid]['name']);continue
        new_contacts.append(ai.contact_payload(contacts[cid],label))
    social={x['id']:x for x in preview['social']};lines=[l for l in str(data.get('social_links') or '').splitlines() if l.strip()];added_social=[]
    if any(x not in social for x in body.social):raise HTTPException(422,'Rede social inválida.')
    for sid in dict.fromkeys(body.social):
        item=social[sid]
        if not any(item['url'].rstrip('/') in l for l in lines):lines.append(f"{item['network']}: {item['url']}");added_social.append(item['url'])
    if added_social:data['social_links']='\n'.join(lines)
    if not applied and not new_contacts and not added_social:
        if skipped:raise HTTPException(409,'Os itens selecionados já existem na ficha. Nada foi aplicado.')
        raise HTTPException(422,'Nenhum campo selecionado para aplicar.')
    try:
        routes.SupplierInput(name=s.name,stage=s.stage,score=s.score,**{k:v for k,v in data.items() if k in routes.SupplierInput.model_fields and k not in {'name','stage','score','responsible_user_id'}})
        contact_rows=[routes.ContactInput(**c).model_dump() for c in new_contacts]
    except ValidationError:
        raise HTTPException(422,'Um dos valores selecionados não cabe no formato da ficha. Nada foi aplicado.') from None
    s.data=data
    for row in contact_rows:db.add(SupplierContact(supplier_id=s.id,organization_id=s.organization_id,actor_id=auth.user.id,data=row))
    parts=[f'Fonte: {label}.',f'{len(applied)} campo(s) aplicado(s).']
    if contact_rows:parts.append(f'{len(contact_rows)} contato(s) adicionado(s).')
    if added_social:parts.append(f'{len(added_social)} rede(s) social(is) adicionada(s).')
    parts.append(f'Responsável: {auth.user.name}.')
    service.audit(db,s,auth.user,'ai_fields_applied',{'summary':'Dados cadastrais atualizados com auxílio de IA.','description':' '.join(parts),
        'source_type':run.data['source']['type'],'fields':[a['label'] for a in applied],'contacts':[c['name'] for c in contact_rows],
        'model':run.model,'run_id':str(run.id)})
    run.status='applied'
    run.data={**run.data,'applied':{'at':datetime.now(timezone.utc).isoformat(),'by':str(auth.user.id),'fields':applied,
        'contacts':[c['name'] for c in contact_rows],'social':added_social,'skipped_duplicates':skipped}}
    service.touch(s)
    db.commit()
    return {'applied_fields':len(applied),'contacts':len(contact_rows),'social':len(added_social),'skipped_duplicates':skipped,'summary':' '.join(parts)}


# --- Novo fornecedor com IA: analysis before the supplier exists, creation only after review --------------

EMAIL=re.compile(r'^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$')
PHONE=re.compile(r'^[+\d\s().\-/]{6,40}$')

def pending_root(settings,user):
    return routes.storage(settings)/str(user.organization_id)/'_pendentes'

def purge_pending(settings,user):
    """Fichas of analyses never confirmed are removed after the preview expires (no supplier was ever created)."""
    root=pending_root(settings,user)
    if not root.is_dir():return
    limit=datetime.now(timezone.utc).timestamp()-ai.RUN_TTL.total_seconds()
    for item in root.iterdir():
        if item.is_file() and item.stat().st_mtime<limit:item.unlink(missing_ok=True)

def new_run(db,user,run_id):
    run=db.scalar(select(SupplierAIRun).where(SupplierAIRun.id==run_id,SupplierAIRun.organization_id==user.organization_id,
                                              SupplierAIRun.actor_id==user.id))
    if run is None or not run.data.get('new_supplier'):raise HTTPException(404,'Análise não encontrada.')
    return run

def suggested(preview,key):
    field=next((f for f in preview['fields'] if f['key']==key),None)
    return field['suggestions'][0]['value'] if field and len({s['value'] for s in field['suggestions']})==1 else ''

def new_preview(db,user,run):
    preview=ai.preview(run)
    values={k:suggested(preview,k) for k in ('legal_name','trade_name','cnpj','company_registration','website')}
    values['name']=values['trade_name'] or values['legal_name'];values['website']=values['website'] or run.data['source'].get('url','')
    preview.update(mode='new',all_fields=[{'key':k,'label':l,'group':g,'kind':kind} for k,(l,g,kind) in ai.FIELDS.items()],duplicates=service.find_duplicates(db,user.organization_id,values),
                   document={k:run.data['pending_document'][k] for k in ('original_name','size')} if run.data.get('pending_document') else None,
                   defaults={'name':values['name'],'stage':next(iter(service.STAGES)),'score':'morno','responsible_user_id':str(user.id),
                             'website':values['website']})
    return preview

@router.post('/ai/analisar',dependencies=routes.WRITE)
def analyze_new(db:DbSession,auth:CurrentAuth,settings:AppSettings,file:Annotated[UploadFile|None,File()]=None,
                url:Annotated[str,Form(max_length=500)]=''):
    """Novo fornecedor com IA: ficha and/or site → preview. Never creates a Supplier."""
    service.active(auth.user)
    has_file=file is not None and bool(file.filename);website=url.strip()
    if not has_file and not website:raise HTTPException(422,'Envie a ficha cadastral e/ou informe o site oficial.')
    ready(db,auth.user,settings);purge_pending(settings,auth.user)
    source={'type':'combined' if has_file and website else 'supplier_document' if has_file else 'website'}
    extra={'new_supplier':True};doc=path=None;suffix=''
    if has_file:
        pending_id=uuid.uuid4();path=pending_root(settings,auth.user)/str(pending_id)
        meta=routes.save_upload(file,path);suffix=Path(meta['original_name']).suffix.lower()
        if suffix not in READABLE:path.unlink(missing_ok=True);raise HTTPException(422,'Formato não suportado para leitura com IA.')
        doc=SimpleNamespace(id=pending_id,data={'original_name':meta['original_name']})
        source.update(document_id=str(pending_id),document_name=meta['original_name'],category='Ficha cadastral')
        extra['pending_document']={**meta,'id':str(pending_id),'uploaded_by':str(auth.user.id),'uploaded_at':datetime.now(timezone.utc).isoformat()}
    snap={'data':{k:'' for k in list(ai.FIELDS)+['social_links']},'contacts':[]}
    try:
        run=run_analysis(db,auth.user,settings,organization_id=auth.user.organization_id,supplier_id=None,snap=snap,source=source,
                         doc=doc,path=path,suffix=suffix,website=website,site=bool(website),extra=extra)
    except BaseException:
        if path is not None:path.unlink(missing_ok=True)
        raise
    preview=new_preview(db,auth.user,run)
    run.data={**run.data,'duplicates_at_analysis':[{'id':d['id'],'reasons':d['reasons']} for d in preview['duplicates']]};db.commit()
    return preview

class Discard(routes.Fields):
    run_id: uuid.UUID

@router.post('/ai/descartar',dependencies=routes.WRITE)
def discard_new(body:Discard,db:DbSession,auth:CurrentAuth,settings:AppSettings):
    """Cancel: removes the pending ficha; the run stays only as audit. Nothing was created."""
    run=new_run(db,auth.user,body.run_id)
    if run.status=='ok':
        if run.data.get('pending_document'):(pending_root(settings,auth.user)/run.data['pending_document']['id']).unlink(missing_ok=True)
        run.status='cancelled';run.data={**run.data,'cancelled_at':datetime.now(timezone.utc).isoformat()};db.commit()
    return {'ok':True}

class NewField(routes.Fields):
    value: str=Field(default='',max_length=4000)
    choice: int|None=Field(default=None,ge=0,le=50)

class AlsoContact(routes.Fields):
    key: str
    choice: int=Field(ge=0,le=50)

class CreateInput(routes.Fields):
    run_id: uuid.UUID
    name: str=Field(min_length=1,max_length=200)
    responsible_user_id: uuid.UUID|None=None
    stage: str|None=None
    score: str|None=None
    fields: dict[str,NewField]=Field(default_factory=dict)
    also_contacts: list[AlsoContact]=Field(default_factory=list,max_length=20)
    contacts: list[str]=Field(default_factory=list,max_length=100)
    social: list[str]=Field(default_factory=list,max_length=50)
    attach_document: bool=True
    allow_name_duplicate: bool=False

def checked(key,value):
    """Server-side validation of every reviewed/edited value (JS validation is only a convenience)."""
    label,_,kind=ai.FIELDS[key];value=value.strip()
    if not value:return ''
    if kind=='email' and not EMAIL.match(value):raise HTTPException(422,f'E-mail inválido em {label}.')
    if kind=='phone' and (not PHONE.match(value) or len(ai.digits(value))<6):raise HTTPException(422,f'Telefone inválido em {label}.')
    if kind=='url':
        try:web.normalize_url(value)
        except web.Blocked:raise HTTPException(422,f'Endereço inválido em {label}. Use http:// ou https://.') from None
    if key=='cnpj' and len(ai.digits(value))==14 and not ai.valid_cnpj(value):raise HTTPException(422,'CNPJ inválido (dígito verificador).')
    return value

def lock_creation(db,organization_id):
    if db.get_bind().dialect.name=='postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'),{'key':'suppliers:create:'+str(organization_id)})

@router.post('/ai/criar',dependencies=routes.WRITE)
def create_new(body:CreateInput,db:DbSession,auth:CurrentAuth,settings:AppSettings):
    """Creates Supplier + contacts + ficha + history + run link in ONE transaction, after rechecking duplicates."""
    user=auth.user;run=new_run(db,user,body.run_id)
    if run.status!='ok':raise HTTPException(409,'Esta análise já foi usada ou descartada. Faça uma nova análise.')
    if ai.expired(run):raise HTTPException(409,'Análise expirada. Faça uma nova análise.')
    preview=ai.preview(run);by_key={f['key']:f for f in preview['fields']};label=ai.source_label(run.data['source'])
    if set(body.fields)-set(ai.FIELDS):raise HTTPException(422,'Campo desconhecido.')
    data,provenance={},[]
    for key,item in body.fields.items():
        value=checked(key,item.value);field=by_key.get(key)
        if item.choice is not None and (field is None or item.choice>=len(field['suggestions'])):raise HTTPException(422,'Seleção inválida.')
        if not value:continue
        data[key]=value
        if item.choice is None:origin={'origin':'manual'}
        else:
            s=field['suggestions'][item.choice]
            origin={'origin':'ia' if ai.same_value(ai.FIELDS[key][2],s['value'],value) else 'editado','suggested':s['value'],
                    **{k:s[k] for k in ('source_type','source','document_id','page','confidence') if k in s}}
        provenance.append({'key':key,'label':ai.FIELDS[key][0],**origin})
    contacts,seen=[],[]
    def add_contact(contact):
        if not ai.duplicate_contact(contact,seen):seen.append(contact);contacts.append(ai.contact_payload(contact,label))
    for extra in body.also_contacts:  # "cadastrar ambos": the other divergent value also becomes a contact
        field=by_key.get(extra.key)
        if field is None or field['kind'] not in {'email','phone'} or extra.choice>=len(field['suggestions']):raise HTTPException(422,'Seleção inválida.')
        value=field['suggestions'][extra.choice]['value']
        add_contact({'name':field['label'],'role':'','department':'','email':value if field['kind']=='email' else '',
                     'phone':value if extra.key=='phone' else '','mobile':value if extra.key=='mobile' else '','whatsapp':value if extra.key=='whatsapp' else ''})
    found={c['id']:c for c in preview['contacts']}
    if len(set(body.contacts))!=len(body.contacts) or any(c not in found for c in body.contacts):raise HTTPException(422,'Contato inválido.')
    for cid in body.contacts:add_contact(found[cid])
    social={x['id']:x for x in preview['social']}
    if any(x not in social for x in body.social):raise HTTPException(422,'Rede social inválida.')
    lines=[l for l in data.get('social_links','').splitlines() if l.strip()]
    for sid in dict.fromkeys(body.social):
        if not any(social[sid]['url'].rstrip('/') in l for l in lines):lines.append(f"{social[sid]['network']}: {social[sid]['url']}")
    if lines:data['social_links']='\n'.join(lines)
    try:
        payload=routes.SupplierInput(name=body.name.strip(),responsible_user_id=body.responsible_user_id,stage=body.stage or next(iter(service.STAGES)),
                                     score=body.score or 'morno',**data)
        rows=[routes.ContactInput(**c).model_dump() for c in contacts]
    except ValidationError:
        raise HTTPException(422,'Um dos valores não cabe no formato da ficha. Nada foi criado.') from None
    owner=routes.validate_supplier(db,user,payload)  # stage, score and responsible policy of the module
    lock_creation(db,user.organization_id)  # serializes concurrent creations; duplicates rechecked inside the lock
    # The analyzed site identifies the company even if the Site field was left empty.
    duplicates=service.find_duplicates(db,user.organization_id,{**data,'name':payload.name,'website':data.get('website') or run.data['source'].get('url','')})
    strong=any(d['strong'] for d in duplicates)
    if strong or (duplicates and not body.allow_name_duplicate):
        analyzed=aware(run.created_at)
        message=('Este fornecedor foi cadastrado enquanto você revisava a análise.' if strong and any(
                     d['strong'] and d['created_at'] and aware(datetime.fromisoformat(d['created_at']))>=analyzed for d in duplicates) else
                 'Possível fornecedor já cadastrado.' if strong else 'Existe fornecedor com nome semelhante. Confirme para cadastrar mesmo assim.')
        db.rollback()
        raise HTTPException(409,{'message':message,'duplicates':duplicates,'can_continue':not strong})
    document=run.data.get('pending_document') if body.attach_document else None
    pending=pending_root(settings,user)/document['id'] if document else None
    if pending is not None and not pending.is_file():raise HTTPException(409,'A ficha enviada não está mais disponível. Faça uma nova análise.')
    moved=None
    try:
        s=Supplier(organization_id=user.organization_id,responsible_user_id=owner,name=payload.name,stage=payload.stage,score=payload.score,
                   data=payload.model_dump(mode='json',exclude={'name','stage','score','responsible_user_id'}))
        db.add(s);db.flush()
        for index,row in enumerate(rows):
            db.add(SupplierContact(supplier_id=s.id,organization_id=s.organization_id,actor_id=user.id,data={**row,'is_primary':index==0}))
        if document:
            db.add(SupplierDocument(id=uuid.UUID(document['id']),supplier_id=s.id,organization_id=s.organization_id,actor_id=uuid.UUID(document['uploaded_by']),
                data={**{k:document[k] for k in ('original_name','mime','size','sha256')},'category':'Ficha cadastral',
                      'description':'Ficha enviada no cadastro com IA','status':'Em revisão','valid_until':None,'start_date':None,'version':'',
                      'uploaded_at':document['uploaded_at']}))
        edited=sum(p['origin']=='editado' for p in provenance)
        sources={'combined':'ficha cadastral + site oficial','supplier_document':'ficha cadastral','website':'site oficial'}[run.data['source']['type']]
        parts=[f'Fontes: {sources}.',f'{len(provenance)} campo(s) aplicado(s)'+(f' ({edited} editado(s) manualmente).' if edited else '.'),
               f'{len(rows)} contato(s) cadastrado(s).']+(['Ficha cadastral anexada.'] if document else [])+\
              [f'Responsável: {db.get(type(user),owner).name}.',f'Cadastrado por: {user.name}.']
        service.audit(db,s,user,'supplier_created_ai',{'summary':'Fornecedor cadastrado com auxílio de IA.','description':' '.join(parts),
            'source_type':run.data['source']['type'],'fields':provenance,'contacts':[r['name'] for r in rows],'model':run.model,'run_id':str(run.id)})
        run.supplier_id=s.id;run.status='applied'
        run.data={**run.data,'created':{'at':datetime.now(timezone.utc).isoformat(),'by':str(user.id),'supplier_id':str(s.id),
                  'fields':provenance,'contacts':[r['name'] for r in rows],'document_attached':bool(document)}}
        db.flush()
        if document:
            final=routes.document_path(settings,user,s.id,document['id']);final.parent.mkdir(parents=True,exist_ok=True)
            os.replace(pending,final);moved=final
        db.commit()
    except BaseException:
        db.rollback()
        if moved is not None:os.replace(moved,pending)  # the ficha stays with the pending analysis; nothing is half-created
        raise
    return {'id':str(s.id),'summary':' '.join(parts)}
