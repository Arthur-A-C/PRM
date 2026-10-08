import json
import re
from typing import Annotated

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response

from app.dependencies import CurrentAuth
from app.services.security import secrets_match

from app.services.qwen import (
    analyze_product_with_qwen,
    extract_and_translate_specs_with_qwen,
)
from app.services.datasheet_choice import generate_choice_datasheet
from app.services.datasheet_portwell import generate_portwell_datasheet
from app.services.datasheet_sag import generate_sag_datasheet


router = APIRouter(
    prefix="/api/v1/digitalizacao",
    tags=["digitalizacao"],
)


def _require_authorized(auth: CurrentAuth, csrf_token: str | None) -> None:
    if not csrf_token or not secrets_match(auth.login_session.csrf_hash, csrf_token):
        raise HTTPException(status_code=403, detail="Token CSRF inválido.")


def _safe_filename(value: str) -> str:
    value = value.strip().upper()
    value = re.sub(r"[^A-Z0-9._-]+", "-", value)
    value = value.strip("-._")
    return value or "PRODUTO"


@router.post("/extrair-especificacoes")
async def extrair_especificacoes(
    codigo: Annotated[str, Form(...)],
    nome: Annotated[str, Form(...)],
    datasheet: Annotated[UploadFile, File(...)],
    auth: CurrentAuth,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
):
    _require_authorized(auth, csrf_token)
    codigo = codigo.strip()
    nome = nome.strip()

    if not codigo:
        raise HTTPException(
            status_code=400,
            detail="O código do produto é obrigatório.",
        )

    if not nome:
        raise HTTPException(
            status_code=400,
            detail="O nome do produto é obrigatório.",
        )

    filename = datasheet.filename or "datasheet.pdf"

    if (
        datasheet.content_type != "application/pdf"
        and not filename.lower().endswith(".pdf")
    ):
        raise HTTPException(
            status_code=400,
            detail="O datasheet do fornecedor deve ser um arquivo PDF.",
        )

    pdf_bytes = await datasheet.read()

    if not pdf_bytes:
        raise HTTPException(
            status_code=400,
            detail="O PDF enviado está vazio.",
        )

    try:
        extracted_text = extract_and_translate_specs_with_qwen(
    codigo=codigo,
    nome=nome,
    pdf_bytes=pdf_bytes,
    pdf_filename=filename,
)

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao extrair texto do PDF: {exc}",
        ) from exc

    return {
        "success": True,
        "codigo": codigo,
        "filename": filename,
        "text": extracted_text,
    }


@router.post("/analisar")
async def analisar_produto(
    empresa: Annotated[str, Form(...)],
    codigo: Annotated[str, Form(...)],
    nome: Annotated[str, Form(...)],
    informacoes_adicionais: Annotated[str, Form(...)],
    auth: CurrentAuth,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
):
    _require_authorized(auth, csrf_token)
    codigo = codigo.strip()
    nome = nome.strip()
    empresa = empresa.strip().lower()
    informacoes_adicionais = informacoes_adicionais.strip()

    if not codigo:
        raise HTTPException(
            status_code=400,
            detail="O código do produto é obrigatório.",
        )

    if not nome:
        raise HTTPException(
            status_code=400,
            detail="O nome do produto é obrigatório.",
        )

    if empresa not in {"portwell", "choice", "sag"}:
        raise HTTPException(
            status_code=400,
            detail="Empresa inválida.",
        )

    if not informacoes_adicionais:
        raise HTTPException(
            status_code=400,
            detail=(
                "Extraia as especificações do PDF ou informe "
                "as especificações manualmente antes da análise."
            ),
        )

    try:
        resultado = analyze_product_with_qwen(
            codigo=codigo,
            nome=nome,
            informacoes_adicionais=informacoes_adicionais,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Erro durante a análise com Qwen: {exc}",
        ) from exc

    return {
        "success": True,
        "empresa": empresa,
        "codigo": codigo,
        "data": resultado,
    }


@router.post("/gerar-datasheet")
async def gerar_datasheet(
    empresa: Annotated[str, Form(...)],
    codigo: Annotated[str, Form(...)],
    analysis_json: Annotated[str, Form(...)],
    auth: CurrentAuth,
    imagens: Annotated[list[UploadFile] | None, File()] = None,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
):
    _require_authorized(auth, csrf_token)
    empresa = empresa.strip().lower()
    codigo = codigo.strip()

    if not codigo:
        raise HTTPException(status_code=400, detail="O código do produto é obrigatório.")

    if empresa not in {"portwell", "choice", "sag"}:
        raise HTTPException(status_code=400, detail="Empresa inválida.")

    try:
        analysis = json.loads(analysis_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="O resultado da análise possui JSON inválido.",
        ) from exc

    if not isinstance(analysis, dict):
        raise HTTPException(
            status_code=400,
            detail="O resultado da análise deve ser um objeto JSON.",
        )

    image_bytes: list[bytes] = []

    allowed_image_types = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
    }

    for imagem in imagens or []:
        if imagem.content_type not in allowed_image_types:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"A imagem '{imagem.filename}' possui "
                    "um formato não suportado."
                ),
            )

        image_bytes.append(await imagem.read())

    try:
        if empresa == "portwell":
            pdf_bytes = generate_portwell_datasheet(
                data=analysis,
                images=image_bytes,
            )

        elif empresa == "choice":
            pdf_bytes = generate_choice_datasheet(
                data=analysis,
                images=image_bytes,
                codigo=codigo,
            )

        else:
            pdf_bytes = generate_sag_datasheet(
                data=analysis,
                images=image_bytes,
                codigo=codigo,
            )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar o datasheet: {exc}",
        ) from exc

    filename = f"{_safe_filename(codigo)}_Datasheet.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )
