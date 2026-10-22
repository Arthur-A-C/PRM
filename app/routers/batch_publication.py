"""Digitalização e Publicação em Lote. Owner-scoped; paid generation and store writes stay worker-only."""
import os
from typing import Annotated, Literal

from dotenv import dotenv_values
from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.dependencies import AppSettings, CurrentAuth
from app.routers.registration import require_manager
from app.routers.store_integrations import authorized_settings
from app.services.batch_publication import Pipelines
from app.services.datasheet_batches import PROJECT

router = APIRouter(prefix="/api/v1/publicacao-lote", tags=["publicacao-lote"])


class Selection(BaseModel):
    skus: list[str] | None = None
    items: list[int] | None = None
    replace_main: list[str] = []


def scope(auth):
    return str(auth.user.organization_id), str(auth.user.id)


def pipelines(auth, settings):
    return Pipelines(settings, authorized_settings(auth))


def run(action):
    try:
        return action()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("")
async def upload(auth: CurrentAuth, settings: AppSettings, empresa: Annotated[Literal["choice", "sag", "portwell"], Form()],
                 arquivo: Annotated[UploadFile, File()], pasta_raiz: Annotated[str, Form()] = "",
                 csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    require_manager(auth, csrf_token)
    service = pipelines(auth, settings)
    try:
        raw = await arquivo.read(settings.batch_upload_mib * 1024**2 + 1)
        identifier = await run_in_threadpool(lambda: run(lambda: service.create(raw, empresa, *scope(auth), root=pasta_raiz)))
        return service.overview(identifier, *scope(auth))
    finally:
        await arquivo.close()


@router.get("")
def history(auth: CurrentAuth, settings: AppSettings):
    return {"items": pipelines(auth, settings).history(*scope(auth))}


@router.get("/{identifier}")
def overview(identifier: str, auth: CurrentAuth, settings: AppSettings):
    return run(lambda: pipelines(auth, settings).overview(identifier, *scope(auth)))


def mutate(identifier, auth, settings, csrf_token, action):
    require_manager(auth, csrf_token)
    service = pipelines(auth, settings)
    result = run(lambda: action(service))
    return {"result": result, **service.overview(identifier, *scope(auth))}


@router.post("/{identifier}/processar")
def process(identifier: str, auth: CurrentAuth, settings: AppSettings, body: Selection | None = None,
            csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    # Same paid-generation gate as Geração em Lote: explicit start, configured model, worker-only execution.
    model = os.environ.get("DATASHEET_MODEL") or dotenv_values(PROJECT / ".env").get("DATASHEET_MODEL", "")
    return mutate(identifier, auth, settings, csrf_token,
                  lambda s: s.process(identifier, *scope(auth), model, items=(body or Selection()).items))


@router.post("/{identifier}/reprocessar")
def retry(identifier: str, auth: CurrentAuth, settings: AppSettings, body: Selection | None = None,
          csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    model = os.environ.get("DATASHEET_MODEL") or dotenv_values(PROJECT / ".env").get("DATASHEET_MODEL", "")
    return mutate(identifier, auth, settings, csrf_token,
                  lambda s: s.process(identifier, *scope(auth), model, items=(body or Selection()).items, retry=True))


@router.post("/{identifier}/pausar")
def pause(identifier: str, auth: CurrentAuth, settings: AppSettings,
          csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    return mutate(identifier, auth, settings, csrf_token, lambda s: s.pause(identifier, *scope(auth)))


@router.post("/{identifier}/preparar")
def prepare(identifier: str, auth: CurrentAuth, settings: AppSettings, body: Selection | None = None,
            csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    return mutate(identifier, auth, settings, csrf_token, lambda s: s.handoff(identifier, *scope(auth), (body or Selection()).skus))


@router.post("/{identifier}/aprovar")
def approve(identifier: str, auth: CurrentAuth, settings: AppSettings, body: Selection | None = None,
            csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    body = body or Selection()
    return mutate(identifier, auth, settings, csrf_token, lambda s: s.approve(identifier, *scope(auth), body.skus, body.replace_main))


@router.post("/{identifier}/publicar")
def publish(identifier: str, auth: CurrentAuth, settings: AppSettings, body: Selection | None = None,
            csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    return mutate(identifier, auth, settings, csrf_token, lambda s: s.publish(identifier, *scope(auth), (body or Selection()).skus))


@router.post("/{identifier}/retomar")
def resume(identifier: str, auth: CurrentAuth, settings: AppSettings,
           csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    return mutate(identifier, auth, settings, csrf_token, lambda s: s.resume(identifier, *scope(auth)))


@router.get("/{identifier}/exportar")
def export(identifier: str, auth: CurrentAuth, settings: AppSettings):
    """Backup/external use: the same packages handed to publication (no supplier datasheet)."""
    raw, _, _ = run(lambda: pipelines(auth, settings).archive(identifier, *scope(auth)))
    return Response(raw, media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="publicacao-lote.zip"', "Cache-Control": "private, no-store"})
