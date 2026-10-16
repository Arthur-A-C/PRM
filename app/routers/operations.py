from fastapi import APIRouter, HTTPException

from app.dependencies import CurrentAuth
from app.services.operations_overview import operations_overview


router = APIRouter(prefix="/api/v1/operations", tags=["operações"])


@router.get("/overview")
def overview(auth: CurrentAuth) -> dict:
    # Same access rule as reading digitalization runs.
    if auth.user.role != "gestor":
        raise HTTPException(status_code=403, detail="Somente gestores consultam as execuções de digitalização.")
    return operations_overview()
