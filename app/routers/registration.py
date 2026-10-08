"""Review and local exports for automated registration inside Digitalização."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ValidationError
import httpx

from app.dependencies import CurrentAuth
from app.schemas.registration import RegistrationProduct
from app.services.registration_cigam import export_cigam_xlsx
from app.services.registration_description import build_description
from app.services.digitalization_storage import verify_package
from app.services.registration_exports import load_company_export
from app.services.registration_files import classify_files, configured_root, find_product_folder
from app.services.registration_package import build_package, safe_component
from app.services.registration_sheets import preview_sheet
from app.services.registration_woo_csv import export_skus_only, export_woo_csv, parse_woo_export
from app.services.registration_woo_api import preview_live_product
from app.services.security import secrets_match


router = APIRouter(prefix="/api/v1/digitalizacao/cadastro", tags=["cadastro automatizado"])


def require_manager(auth: CurrentAuth, csrf_token: str | None) -> None:
    if auth.user.role != "gestor":
        raise HTTPException(status_code=403, detail="Somente gestores podem preparar cadastros.")
    if not csrf_token or not secrets_match(auth.login_session.csrf_hash, csrf_token):
        raise HTTPException(status_code=403, detail="Token CSRF inválido.")


def parse_product(raw: str) -> RegistrationProduct:
    try:
        return RegistrationProduct.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_context=False)) from exc


class DescriptionRequest(BaseModel):
    product: RegistrationProduct
    run_id: str | None = None


def require_validated_run(run_id: str | None, product: RegistrationProduct) -> dict:
    if not run_id:
        raise HTTPException(status_code=409, detail="Finalize e valide a digitalização antes do cadastro.")
    try:
        record = verify_package(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if (record.get("status") != "validated" or record.get("company") != product.company
            or record.get("sku") != product.sku or record.get("name") != product.technical_name):
        raise HTTPException(status_code=409, detail="Pacote não validado para esta empresa e SKU.")
    return record


class FilePreviewRequest(BaseModel):
    company: str
    sku: str
    run_id: str | None = None


@router.post("/descricao")
def description(payload: DescriptionRequest, auth: CurrentAuth, csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    require_manager(auth, csrf_token)
    require_validated_run(payload.run_id, payload.product)
    html, warnings = build_description(payload.product)
    return {"html": html, "warnings": warnings, "status": "needs_review"}


@router.post("/woocommerce/previa")
def woo_preview(payload: DescriptionRequest, auth: CurrentAuth, csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    require_manager(auth, csrf_token)
    require_validated_run(payload.run_id, payload.product)
    try:
        return preview_live_product(payload.product)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Falha na consulta somente leitura à loja; nenhum produto foi alterado.")


@router.post("/arquivos/previa")
def files_preview(payload: FilePreviewRequest, auth: CurrentAuth, csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None):
    require_manager(auth, csrf_token)
    try:
        if payload.run_id:
            record = verify_package(payload.run_id)
            if record["company"] != payload.company or record["sku"] != payload.sku:
                raise ValueError("Execução não corresponde à empresa e ao SKU selecionados.")
            return {"found": True, "sku": payload.sku, "run_id": payload.run_id, "files": classify_files(Path(record["folder_path"]))}
        folder = find_product_folder(configured_root(payload.company), payload.sku)
        if folder is None:
            return {"found": False, "sku": payload.sku, "files": None}
        return {"found": True, "sku": payload.sku, "files": classify_files(folder)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/planilha/previa")
async def sheet_preview(
    auth: CurrentAuth,
    empresa: Annotated[str, Form(...)],
    arquivo: Annotated[UploadFile, File(...)],
    export_file: Annotated[UploadFile | None, File()] = None,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
):
    require_manager(auth, csrf_token)
    if empresa not in {"choice", "sag", "portwell"}:
        raise HTTPException(status_code=400, detail="Empresa inválida.")
    try:
        export_content = await export_file.read(25 * 1024 * 1024 + 1) if export_file else load_company_export(empresa)
        template = parse_woo_export(export_content)
        existing_skus = set(template.rows_by_sku)
        return preview_sheet(
            await arquivo.read(20 * 1024 * 1024 + 1),
            arquivo.filename or "", empresa, existing_skus,
            {key: value[0] for key, value in template.names.items()},
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/woocommerce/csv")
async def woo_csv(
    auth: CurrentAuth,
    product_json: Annotated[str, Form(...)],
    run_id: Annotated[str, Form(...)],
    export_file: Annotated[UploadFile | None, File()] = None,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
):
    require_manager(auth, csrf_token)
    product = parse_product(product_json)
    require_validated_run(run_id, product)
    if product.validation_status != "approved":
        raise HTTPException(status_code=409, detail="Aprovação explícita necessária antes do CSV WooCommerce.")
    try:
        export_content = await export_file.read(25 * 1024 * 1024 + 1) if export_file else load_company_export(product.company)
        template = parse_woo_export(export_content)
        content, warnings = export_woo_csv(product, template)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content, media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_component(product.sku)}_woo.csv"',
            "X-PRM-Review-Warnings": str(len(warnings)),
        },
    )


@router.post("/cigam/xlsx")
async def cigam_xlsx(
    auth: CurrentAuth,
    product_json: Annotated[str, Form(...)],
    template_file: Annotated[UploadFile, File(...)],
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
):
    require_manager(auth, csrf_token)
    product = parse_product(product_json)
    try:
        content, warnings = export_cigam_xlsx(product, await template_file.read(5 * 1024 * 1024 + 1))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_component(product.sku)}_cigam.xlsx"',
            "X-PRM-Pending-Fields": str(len(warnings)),
        },
    )


@router.post("/pacote/zip")
async def package_zip(
    auth: CurrentAuth,
    product_json: Annotated[str, Form(...)],
    images: Annotated[list[UploadFile] | None, File()] = None,
    rotations_json: Annotated[str, Form()] = "[]",
    generated_datasheet: Annotated[UploadFile | None, File()] = None,
    source_datasheet: Annotated[UploadFile | None, File()] = None,
    drawing_3d: Annotated[UploadFile | None, File()] = None,
    size: Annotated[str, Form()] = "1200",
    quality: Annotated[int, Form()] = 90,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
):
    require_manager(auth, csrf_token)
    product = parse_product(product_json)
    try:
        rotations = json.loads(rotations_json)
        if not isinstance(rotations, list) or len(rotations) != len(images or []):
            raise ValueError("Rotações e imagens não correspondem.")
        actual_size = None if size == "original" else int(size)
        image_data = [
            (upload.filename or f"{index}.jpg", await upload.read(25 * 1024 * 1024 + 1), rotations[index])
            for index, upload in enumerate(images or [])
        ]
        files = []
        for role, upload in (
            ("generated_datasheet", generated_datasheet),
            ("source_datasheet", source_datasheet),
            ("drawing_3d", drawing_3d),
        ):
            if upload:
                files.append((role, upload.filename or role, await upload.read(50 * 1024 * 1024 + 1)))
        content, manifest = build_package(product, image_data, files, size=actual_size, quality=quality)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_component(product.sku)}_pacote.zip"'},
    )


@router.post("/skus/csv")
def sku_csv(
    auth: CurrentAuth,
    codes: list[str],
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
):
    require_manager(auth, csrf_token)
    if len(codes) > 50000 or any(not code or code.startswith(("=", "+", "-", "@")) for code in codes):
        raise HTTPException(status_code=422, detail="Lista de códigos inválida.")
    return Response(
        export_skus_only(codes), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="codigos_cigam.csv"'},
    )
