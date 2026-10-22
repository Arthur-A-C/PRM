from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Response

from app.dependencies import CurrentAuth
from app.routers.registration import require_manager
from app.services.store_config import StoreSettings
from app.services.store_connections import ConnectionHistory, check_company

router = APIRouter(prefix="/api/v1/integracoes/lojas", tags=["integrações somente leitura"])
Company = Literal["choice", "sag", "portwell"]


def authorized_settings(auth):
    if auth.user.role not in {"gestor", "desenvolvedor"}:
        raise HTTPException(403, "Somente gestores podem consultar integrações.")
    settings = StoreSettings()
    if not settings.organization_id:
        raise HTTPException(503, "Configure PRM_STORE_ORGANIZATION_ID no backend para autorizar a organização.")
    if str(auth.user.organization_id) != settings.organization_id:
        raise HTTPException(403, "Integração não autorizada para esta organização.")
    return settings


@router.get("")
def status(auth: CurrentAuth, response: Response):
    settings = authorized_settings(auth)
    response.headers["Cache-Control"] = "private, no-store"
    return {"items":ConnectionHistory(settings).list(auth.user.organization_id)}


@router.post("/{company}/testar")
def test_connection(company: Company, auth: CurrentAuth, response: Response,
                    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    require_manager(auth, csrf_token)
    settings = authorized_settings(auth)
    result = check_company(company, settings)
    ConnectionHistory(settings).save(auth.user.organization_id, result)
    response.headers["Cache-Control"] = "private, no-store"
    return result
