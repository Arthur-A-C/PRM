"""Resolução de imagens em pasta. Managers only; mutations require CSRF and explicit confirmation."""
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.dependencies import CurrentAuth
from app.routers.registration import require_manager
from app.services import image_resolution as tool

router = APIRouter(prefix="/api/v1/imagens", tags=["resolucao-imagens"])


class Folder(BaseModel):
    caminho: str
    subpastas: bool = True
    tamanho: int = 1500
    mover_para_backup: bool = True
    confirmar: bool = False


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
        body.caminho, recursive=body.subpastas, size=body.tamanho, backup=body.mover_para_backup, confirmed=body.confirmar)))
    return task.public()


@router.post("/restaurar")
async def restore(body: Folder, auth: CurrentAuth, csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    require_manager(auth, csrf_token)
    task = await run_in_threadpool(lambda: run(lambda: tool.start_restore(body.caminho, confirmed=body.confirmar)))
    return task.public()


@router.get("/tarefas/{identifier}")
def status(identifier: str, auth: CurrentAuth):
    manager(auth)
    return run(lambda: tool.task(identifier).public())


@router.post("/tarefas/{identifier}/parar")
def stop(identifier: str, auth: CurrentAuth, csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    require_manager(auth, csrf_token)
    return run(lambda: tool.stop(identifier).public())
