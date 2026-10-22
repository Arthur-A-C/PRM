"""Resolução de imagens. Managers only; mutations require CSRF and explicit confirmation.

Padrão: pasta enviada pelo navegador (/api/v1/envios, perfil "imagens") processada numa área de
trabalho isolada do usuário e devolvida em ZIP. Opcional: pasta do servidor em PRM_IMAGE_TOOL_ROOTS.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.dependencies import AppSettings, CurrentAuth
from app.routers.registration import require_manager
from app.services import image_resolution as tool
from app.services.local_uploads import Uploads

router = APIRouter(prefix="/api/v1/imagens", tags=["resolucao-imagens"])


class Folder(BaseModel):
    caminho: str
    subpastas: bool = True
    tamanho: int = 1500
    mover_para_backup: bool = True
    confirmar: bool = False


class Options(BaseModel):
    subpastas: bool = True
    tamanho: int = 1500
    confirmar: bool = False


def owner(auth):
    return str(auth.user.organization_id), str(auth.user.id)


def manager(auth):
    if auth.user.role not in {"gestor", "desenvolvedor"}:
        raise HTTPException(403, "Somente gestores podem alterar imagens em pastas.")


def run(action):
    try:
        return action()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except OSError:
        raise HTTPException(422, "Pasta inacessível pelo servidor do PRM.") from None


@router.get("/pastas")
def folders(auth: CurrentAuth, caminho: str | None = None):
    manager(auth)
    return run(lambda: tool.list_folders(caminho))


@router.post("/previa")
async def preview(body: Folder, auth: CurrentAuth, csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    require_manager(auth, csrf_token)
    return await run_in_threadpool(lambda: run(lambda: tool.preview(body.caminho, body.subpastas, body.tamanho)))


@router.post("/processar")
async def convert(body: Folder, auth: CurrentAuth, csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    require_manager(auth, csrf_token)
    task = await run_in_threadpool(lambda: run(lambda: tool.start_conversion(
        body.caminho, recursive=body.subpastas, size=body.tamanho, backup=body.mover_para_backup, confirmed=body.confirmar,
        owner=owner(auth))))
    return task.public()


@router.post("/restaurar")
async def restore(body: Folder, auth: CurrentAuth, csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    require_manager(auth, csrf_token)
    task = await run_in_threadpool(lambda: run(lambda: tool.start_restore(body.caminho, confirmed=body.confirmar, owner=owner(auth))))
    return task.public()


@router.get("/tarefas/{identifier}")
def status(identifier: str, auth: CurrentAuth):
    manager(auth)
    return run(lambda: tool.task(identifier, owner(auth)).public())


@router.post("/tarefas/{identifier}/parar")
def stop(identifier: str, auth: CurrentAuth, csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    require_manager(auth, csrf_token)
    return run(lambda: tool.stop(identifier, owner(auth)).public())


# --- Pasta enviada do computador do usuário ------------------------------------------------------

def workspace(envio, auth, settings):
    files, record = Uploads(settings).workspace(envio, *owner(auth), "imagens")
    return files, record["folder"] or "Imagens enviadas"


@router.post("/envios/{envio}/previa")
async def upload_preview(envio: str, body: Options, auth: CurrentAuth, settings: AppSettings,
                         csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    require_manager(auth, csrf_token)

    def action():
        root, label = workspace(envio, auth, settings)
        # Server paths stay internal: the user sees the name of the folder they selected.
        return {**tool.summarize(root, body.subpastas, body.tamanho), "root": label, "backup": f"{label}/{tool.BACKUP} (no servidor)"}
    return await run_in_threadpool(lambda: run(action))


@router.post("/envios/{envio}/processar")
async def upload_convert(envio: str, body: Options, auth: CurrentAuth, settings: AppSettings,
                         csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    require_manager(auth, csrf_token)

    def action():
        root, label = workspace(envio, auth, settings)
        return tool.convert_root(root, recursive=body.subpastas, size=body.tamanho, confirmed=body.confirmar,
                                 owner=owner(auth), label=label)
    return (await run_in_threadpool(lambda: run(action))).public()


@router.get("/envios/{envio}/resultado.zip")
async def upload_result(envio: str, auth: CurrentAuth, settings: AppSettings, backup: bool = False):
    manager(auth)

    def action():
        root, label = workspace(envio, auth, settings)
        # One file per download: simultaneous downloads never share or replace a ZIP being streamed.
        return tool.result_archive(root, root.parent / f"resultado-{uuid.uuid4().hex}.zip", include_backup=backup), label
    path, label = await run_in_threadpool(lambda: run(action))
    return FileResponse(path, media_type="application/zip", filename=f"{label}-{'com-backup' if backup else 'convertidas'}.zip",
                        background=BackgroundTask(path.unlink, missing_ok=True))
