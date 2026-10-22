"""Envios do navegador: arquivos/pastas do computador do usuário em blocos retomáveis. Owner-scoped, CSRF."""
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from app.dependencies import AppSettings, CurrentAuth
from app.services.image_resolution import running
from app.services.local_uploads import MIB, OffsetMismatch, Uploads
from app.services.security import secrets_match

router = APIRouter(prefix="/api/v1/envios", tags=["envios"])


class FileEntry(BaseModel):
    caminho: str
    tamanho: int


class NewUpload(BaseModel):
    perfil: Literal["imagens", "lote"]
    pasta: str = ""
    arquivos: list[FileEntry]


def scope(auth):
    return str(auth.user.organization_id), str(auth.user.id)


def require_upload(auth, csrf_token, *, mutation=True):
    if auth.user.role not in {"gestor", "desenvolvedor"}:
        raise HTTPException(403, "Somente gestores podem enviar arquivos ao PRM.")
    if mutation and (not csrf_token or not secrets_match(auth.login_session.csrf_hash, csrf_token)):
        raise HTTPException(403, "Token CSRF inválido.")


def run(action):
    try:
        return action()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("")
def create(body: NewUpload, auth: CurrentAuth, settings: AppSettings,
           csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    require_upload(auth, csrf_token)
    uploads = Uploads(settings)
    files = [f.model_dump() for f in body.arquivos]
    identifier = run(lambda: uploads.create(*scope(auth), body.perfil, files, body.pasta, busy=running))
    return uploads.status(identifier, *scope(auth))


@router.get("/{identifier}")
def status(identifier: str, auth: CurrentAuth, settings: AppSettings):
    require_upload(auth, None, mutation=False)
    return run(lambda: Uploads(settings).status(identifier, *scope(auth)))


@router.put("/{identifier}/arquivos/{index}")
async def chunk(identifier: str, index: int, inicio: int, request: Request, auth: CurrentAuth, settings: AppSettings,
                csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    """Raw bytes of one block starting at ``inicio``. 409 tells the browser where to resume."""
    require_upload(auth, csrf_token)
    limit = settings.upload_chunk_mib * MIB
    body = bytearray()
    try:
        async for piece in request.stream():
            body += piece
            if len(body) > limit:
                raise HTTPException(413, "Bloco maior que o permitido.")
    except ClientDisconnect:
        # Cancelled or dropped mid-block: nothing was written, the browser resumes from the last complete block.
        return Response(status_code=499)
    uploads = Uploads(settings)
    try:
        received, complete = await run_in_threadpool(
            lambda: run(lambda: uploads.write_chunk(identifier, *scope(auth), index, inicio, [bytes(body)])))
    except OffsetMismatch as exc:
        return JSONResponse({"detail": "Posição de retomada diferente.", "recebido": exc.received}, status_code=409)
    return {"recebido": received, "completo": complete}


@router.post("/{identifier}/concluir")
def finish(identifier: str, auth: CurrentAuth, settings: AppSettings,
           csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    require_upload(auth, csrf_token)
    return run(lambda: Uploads(settings).finish(identifier, *scope(auth)))


@router.delete("/{identifier}")
def cancel(identifier: str, auth: CurrentAuth, settings: AppSettings,
           csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    require_upload(auth, csrf_token)
    run(lambda: Uploads(settings).discard(identifier, *scope(auth), busy=running))
    return {"ok": True}


async def batch_source(auth, settings, upload: UploadFile | None, envio: str, limit_mib: int):
    """ZIP enviado diretamente ou montado a partir de uma pasta enviada pelo navegador: (bytes, nome)."""
    if envio:
        return await run_in_threadpool(lambda: run(lambda: Uploads(settings).archive(envio, *scope(auth), limit_mib)))
    if upload is None or not upload.filename:
        raise HTTPException(422, "Selecione um arquivo ZIP ou uma pasta do computador.")
    return await upload.read(limit_mib * MIB + 1), upload.filename


def consume(auth, settings, envio: str):
    """The batch now holds its own copy; the uploaded workspace is no longer needed."""
    if envio:
        try:
            Uploads(settings).discard(envio, *scope(auth))
        except LookupError:
            pass
