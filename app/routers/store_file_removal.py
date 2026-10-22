"""Remoção de arquivos de produtos (images/_wcda_arquivos). Managers only; mutations need CSRF; writes are worker-only."""
import json
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.dependencies import CurrentAuth
from app.routers.registration import require_manager
from app.routers.store_integrations import authorized_settings
from app.services.store_file_removal import Removals, parse_skus
from app.services.store_registration_jobs import Jobs

router = APIRouter(prefix="/api/v1/remocao-arquivos", tags=["remocao-arquivos"])


class Selection(BaseModel):
    skus: list[str] | None = None


def scope(auth):
    return str(auth.user.organization_id), str(auth.user.id)


def service():
    return Removals(Jobs())


def run(action):
    try:
        return action()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("")
async def create(auth: CurrentAuth, empresa: Annotated[Literal["choice", "sag", "portwell"], Form()],
                 modo: Annotated[Literal["all", "gallery", "documents", "main"], Form()],
                 skus: Annotated[str, Form()] = "", planilha: Annotated[UploadFile | None, File()] = None,
                 csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    require_manager(auth, csrf_token)
    settings = authorized_settings(auth)
    try:
        sheet = await planilha.read(5 * 1024**2 + 1) if planilha and planilha.filename else None
        values, duplicates = run(lambda: parse_skus(skus, sheet, planilha.filename if sheet else ""))
        removals = service()
        identifier = run(lambda: removals.create(empresa, *scope(auth), modo, values, settings))
        return {**removals.detail(identifier, *scope(auth)), "duplicates_removed": duplicates}
    finally:
        if planilha: await planilha.close()


@router.get("")
def history(auth: CurrentAuth):
    authorized_settings(auth)
    return {"items": service().history(*scope(auth))}


@router.get("/{identifier}")
def detail(identifier: str, auth: CurrentAuth):
    authorized_settings(auth)
    return run(lambda: service().detail(identifier, *scope(auth)))


def mutate(identifier, auth, csrf_token, action):
    require_manager(auth, csrf_token)
    settings = authorized_settings(auth)
    removals = service()
    result = run(lambda: action(removals, settings))
    return {"result": result, **removals.detail(identifier, *scope(auth))}


@router.post("/{identifier}/aprovar")
def approve(identifier: str, auth: CurrentAuth, body: Selection | None = None,
            csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    return mutate(identifier, auth, csrf_token, lambda r, s: r.approve(identifier, *scope(auth), (body or Selection()).skus))


@router.post("/{identifier}/executar")
def confirm(identifier: str, auth: CurrentAuth, body: Selection | None = None,
            csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    # Only queues approved items; the worker re-checks policy/grant, state and permissions before any write.
    return mutate(identifier, auth, csrf_token, lambda r, s: r.confirm(identifier, *scope(auth), s, (body or Selection()).skus))


@router.post("/{identifier}/pausar")
def pause(identifier: str, auth: CurrentAuth, csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    return mutate(identifier, auth, csrf_token, lambda r, s: r.pause(identifier, *scope(auth)))


@router.post("/{identifier}/cancelar")
def cancel(identifier: str, auth: CurrentAuth, csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    return mutate(identifier, auth, csrf_token, lambda r, s: r.cancel(identifier, *scope(auth)))


@router.post("/{identifier}/reprocessar")
def reprocess(identifier: str, auth: CurrentAuth, csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    return mutate(identifier, auth, csrf_token, lambda r, s: r.reprocess(identifier, *scope(auth)))


@router.get("/{identifier}/relatorio")
def report(identifier: str, auth: CurrentAuth):
    authorized_settings(auth)
    return Response(run(lambda: service().report(identifier, *scope(auth))), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="remocao-arquivos.csv"', "Cache-Control": "private, no-store"})


@router.get("/{identifier}/dry-run")
def dry_run(identifier: str, auth: CurrentAuth):
    authorized_settings(auth)
    data = run(lambda: service().detail(identifier, *scope(auth)))
    return Response(json.dumps(data, ensure_ascii=False), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="remocao-dry-run.json"', "Cache-Control": "private, no-store"})
