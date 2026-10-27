import csv
import io
from typing import Annotated, Literal
from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, StrictBool
import json
from starlette.concurrency import run_in_threadpool
from app.dependencies import AppSettings, CurrentAuth
from app.routers.local_uploads import batch_source, consume
from app.routers.registration import require_manager as _require_manager
from app.routers.store_integrations import authorized_settings as _authorized_settings
from app.services import store_removal_production as access
from app.services.store_registration_jobs import Jobs, parse_skus
from app.services.store_registration_plan import normalize_scope

router=APIRouter(prefix="/api/v1/cadastro-api",tags=["cadastro de arquivos por cargo"])


def authorized_settings(auth):
    try: access.require_role(auth.user)
    except access.PermissionDenied as exc: raise HTTPException(403,str(exc)) from None
    return _authorized_settings(auth)


def require_manager(auth, csrf_token):
    authorized_settings(auth)
    _require_manager(auth,csrf_token)


class Selection(BaseModel):
    skus: list[str] | None = None
    confirmado: StrictBool = False


def execute(action):
    try: return action()
    except access.PermissionDenied as exc: raise HTTPException(403,str(exc)) from None
    except LookupError as exc: raise HTTPException(404,str(exc)) from None
    except ValueError as exc: raise HTTPException(422,str(exc)) from None
    except Exception: raise HTTPException(422,"Arquivo ou operação inválida; nenhum cadastro confirmado.") from None


@router.post("")
async def upload(auth: CurrentAuth, app_settings: AppSettings, empresa: Annotated[Literal["choice","sag","portwell"],Form()],
                 arquivos: Annotated[UploadFile|None,File()]=None, envio: Annotated[str,Form()]="", planilha: Annotated[UploadFile|None,File()]=None,
                 identificacao: Annotated[Literal["csv","folder"],Form()]="csv",
                 pasta_raiz: Annotated[str,Form()]="",
                 escopo: Annotated[str,Form()]="",
                 csrf_token: Annotated[str|None,Header(alias="X-CSRF-Token")]=None):
    require_manager(auth,csrf_token); settings=authorized_settings(auth)
    # What to register is explicit and validated here, never only in the browser.
    scope=execute(lambda:normalize_scope(escopo))
    archive=None
    try:
        records=None
        if planilha and planilha.filename:
            sheet=await planilha.read(5*1024**2+1)
            records=execute(lambda:parse_skus(sheet,planilha.filename or "",details=True,strict=identificacao=="folder"))
        from app.services.upload_limits import check_package
        if envio:
            from app.services.local_uploads import Uploads
            archive,archive_name=await run_in_threadpool(lambda:execute(lambda:Uploads(app_settings).archive(envio,auth.user.organization_id,auth.user.id,app_settings.upload_max_mib,streaming=True)))
        else:
            if not arquivos or not arquivos.filename: raise HTTPException(422,"Selecione ZIP ou pasta.")
            archive=arquivos.file
            # Starlette spools the multipart file to disk: size from the file, never a full read into RAM.
            archive.seek(0,2);execute(lambda:check_package(archive.tell(),app_settings.upload_max_mib));archive.seek(0)
            archive_name=arquivos.filename
        skus=list(records) if records else None
        jobs=Jobs()
        identifier=await run_in_threadpool(lambda:execute(lambda:jobs.create(empresa,auth.user.organization_id,auth.user.id,skus,archive,settings,
            identification=identificacao,archive_name=archive_name,root=pasta_raiz,complements=records,scope=scope)))
        consume(auth,app_settings,envio)
        return jobs.detail(identifier,auth.user.organization_id,auth.user.id)
    finally:
        if envio and archive is not None: archive.close()
        if planilha: await planilha.close()
        if arquivos: await arquivos.close()


@router.get("")
def history(auth: CurrentAuth):
    authorized_settings(auth)
    return {"items":Jobs().history(auth.user.organization_id,auth.user.id)}


@router.get("/{identifier}")
def detail(identifier:str,auth:CurrentAuth):
    authorized_settings(auth)
    return execute(lambda:Jobs().detail(identifier,auth.user.organization_id,auth.user.id))


@router.post("/{identifier}/confirmar")
def confirm(identifier:str,auth:CurrentAuth,body:Selection,csrf_token:Annotated[str|None,Header(alias="X-CSRF-Token")]=None):
    require_manager(auth,csrf_token);settings=authorized_settings(auth)
    jobs=Jobs()
    if not body.skus: raise HTTPException(422,"Selecione pelo menos um SKU para enviar.")
    execute(lambda:jobs.confirm(identifier,auth.user.organization_id,auth.user.id,settings,body.skus,confirmed=body.confirmado))
    return jobs.detail(identifier,auth.user.organization_id,auth.user.id)


class Approval(BaseModel):
    skus: list[str]|None=None
    replace_main: list[str]=[]


@router.post("/{identifier}/aprovar")
def approve(identifier:str,auth:CurrentAuth,body:Approval|None=None,csrf_token:Annotated[str|None,Header(alias="X-CSRF-Token")]=None):
    # Records review of the exact Dry Run only; writes require separate explicit confirmation.
    require_manager(auth,csrf_token);authorized_settings(auth)
    body=body or Approval()
    jobs=Jobs()
    execute(lambda:jobs.approve(identifier,auth.user.organization_id,auth.user.id,body.skus,body.replace_main))
    return jobs.detail(identifier,auth.user.organization_id,auth.user.id)


@router.post("/{identifier}/reprocessar")
def retry(identifier:str,auth:CurrentAuth,body:Selection|None=None,csrf_token:Annotated[str|None,Header(alias="X-CSRF-Token")]=None):
    require_manager(auth,csrf_token);authorized_settings(auth)
    jobs=Jobs()
    execute(lambda:jobs.reprocess(identifier,auth.user.organization_id,auth.user.id,(body or Selection()).skus))
    return jobs.detail(identifier,auth.user.organization_id,auth.user.id)


class Scope(BaseModel):
    escopo: dict[str,StrictBool]
    skus: list[str]|None=None


@router.post("/{identifier}/escopo")
def change_scope(identifier:str,auth:CurrentAuth,body:Scope,csrf_token:Annotated[str|None,Header(alias="X-CSRF-Token")]=None):
    # A new scope always produces a new Dry Run; approvals of the previous one are discarded.
    require_manager(auth,csrf_token);authorized_settings(auth)
    jobs=Jobs()
    execute(lambda:jobs.set_scope(identifier,auth.user.organization_id,auth.user.id,body.escopo,body.skus))
    return jobs.detail(identifier,auth.user.organization_id,auth.user.id)


class MainChoice(BaseModel):
    sku: str
    sha256: str


@router.post("/{identifier}/principal")
def choose_main(identifier:str,auth:CurrentAuth,body:MainChoice,csrf_token:Annotated[str|None,Header(alias="X-CSRF-Token")]=None):
    # Explicit main image of one SKU, among the images of its own Dry Run; redoes that Dry Run.
    require_manager(auth,csrf_token);authorized_settings(auth)
    jobs=Jobs()
    execute(lambda:jobs.choose_main(identifier,auth.user.organization_id,auth.user.id,body.sku,body.sha256))
    return jobs.detail(identifier,auth.user.organization_id,auth.user.id)


@router.post("/{identifier}/restaurar")
def restore(identifier:str,auth:CurrentAuth,body:Selection,csrf_token:Annotated[str|None,Header(alias="X-CSRF-Token")]=None):
    require_manager(auth,csrf_token)
    jobs=Jobs()
    execute(lambda:jobs.request_rollback(identifier,auth.user.organization_id,auth.user.id,body.skus,confirmed=body.confirmado))
    return jobs.detail(identifier,auth.user.organization_id,auth.user.id)


@router.get("/{identifier}/relatorio")
def report(identifier:str,auth:CurrentAuth):
    data=detail(identifier,auth)
    output=io.StringIO(newline="");writer=csv.writer(output)
    writer.writerow(["sku","status","erro","produto_id","imagens_enviar","documentos_incluir","bloqueios","dry_run_aprovado"])
    for i in data["items"]:
        dry=i["dry_run"] or {}
        images=[a["name"] for a in dry.get("images",{}).get("actions",[]) if a["action"]=="upload"]
        documents=[a["label"] for a in dry.get("documents",{}).get("actions",[]) if a["action"]=="add"]
        row=[i["sku"],i["state"],i["error"],str(i["product_id"] or ""),", ".join(images),", ".join(documents),
             " | ".join(i["blockers"]),"sim" if i["approval"] else "não"]
        writer.writerow([("'"+v if v.startswith(("=","+","-","@","\t","\r")) else v) for v in row])
    return Response(output.getvalue().encode("utf-8-sig"),media_type="text/csv",
                    headers={"Content-Disposition":'attachment; filename="cadastro-api.csv"',"Cache-Control":"private, no-store"})


@router.get("/{identifier}/dry-run")
def dry_run(identifier:str,auth:CurrentAuth):
    # detail() enforces organization and owner and excludes private snapshot paths/content.
    data=detail(identifier,auth)
    return Response(json.dumps(data,ensure_ascii=False),media_type="application/json",
                    headers={"Content-Disposition":'attachment; filename="cadastro-dry-run.json"',"Cache-Control":"private, no-store"})
