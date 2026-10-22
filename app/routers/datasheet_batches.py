"""Authenticated, owner-scoped operations; expensive generation is worker-only."""
import os
import tempfile
from typing import Annotated

from dotenv import dotenv_values
from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.dependencies import CurrentAuth, AppSettings
from app.routers.digitalizacao import _require_authorized
from app.routers.local_uploads import batch_source, consume
from app.services.datasheet_batches import BatchStore, PROJECT

router = APIRouter(prefix="/api/v1/digitalizacao/lotes", tags=["digitalizacao-lotes"])


def scope(auth):
    return str(auth.user.organization_id), str(auth.user.id)


def translate(action):
    try:
        return action()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/modelo.csv")
def template(auth: CurrentAuth):
    text = ("codigo,nome,empresa,datasheet_original,descricao,categoria,observacoes\n"
            "10001,Controle Remoto EX,SAG,datasheets/10001.pdf,,,\n"
            "10002,Computador Industrial,PORTWELL,datasheets/10002.pdf,,,\n"
            "10003,Equipamento Industrial,CHOICE,datasheets/10003.pdf,,,\n")
    return Response(text.encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="produtos.csv"'})


@router.post("")
async def upload(auth: CurrentAuth, settings: AppSettings,
                 arquivo: Annotated[UploadFile | None, File()] = None,
                 envio: Annotated[str, Form()] = "",
                 delimitador: Annotated[str, Form()] = ",",
                 identificacao: Annotated[str, Form()] = "csv",
                 empresa: Annotated[str, Form()] = "",
                 pasta_raiz: Annotated[str, Form()] = "",
                 csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    _require_authorized(auth, csrf_token)
    try:
        raw, _ = await batch_source(auth, settings, arquivo, envio, settings.batch_upload_mib)
        store = BatchStore(settings)
        identifier = await run_in_threadpool(lambda: translate(lambda: store.create(
            raw, *scope(auth), delimitador, identification=identificacao, company=empresa, root=pasta_raiz)))
        consume(auth, settings, envio)
        return store.detail(identifier, *scope(auth))
    finally:
        if arquivo:
            await arquivo.close()


@router.get("")
def history(auth: CurrentAuth, settings: AppSettings):
    return {"items": BatchStore(settings).history(*scope(auth))}


@router.get("/{batch}")
def detail(batch: str, auth: CurrentAuth, settings: AppSettings):
    return translate(lambda: BatchStore(settings).detail(batch, *scope(auth)))


def queue(batch, auth, settings, csrf_token, retry=False):
    _require_authorized(auth, csrf_token)
    store = BatchStore(settings)
    model = os.environ.get("DATASHEET_MODEL") or dotenv_values(PROJECT / ".env").get("DATASHEET_MODEL", "")
    translate(lambda: store.enqueue(batch, *scope(auth), model=model, retry=retry))
    return store.detail(batch, *scope(auth))


@router.post("/{batch}/iniciar")
def start(batch: str, auth: CurrentAuth, settings: AppSettings,
          csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    return queue(batch, auth, settings, csrf_token)


@router.post("/{batch}/reprocessar")
def retry(batch: str, auth: CurrentAuth, settings: AppSettings,
          csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    return queue(batch, auth, settings, csrf_token, retry=True)


@router.get("/{batch}/produtos/{item}/pdf")
def pdf(batch: str, item: int, auth: CurrentAuth, settings: AppSettings):
    path, filename = translate(lambda: BatchStore(settings).output_file(batch, item, *scope(auth)))
    return FileResponse(path, filename=filename, media_type="application/pdf",
                        headers={"Cache-Control": "private, no-store"})


@router.get("/{batch}/download")
def download(batch: str, auth: CurrentAuth, settings: AppSettings):
    spool = tempfile.SpooledTemporaryFile(max_size=8 * 1024**2)
    try:
        translate(lambda: BatchStore(settings).bundle(batch, *scope(auth), spool))
        spool.seek(0)
    except BaseException:
        spool.close()
        raise
    def chunks():
        try:
            while chunk := spool.read(65536):
                yield chunk
        finally:
            spool.close()
    return StreamingResponse(chunks(), media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="datasheets_{batch}.zip"',
                 "Cache-Control": "private, no-store"})
