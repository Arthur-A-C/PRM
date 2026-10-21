import json
import asyncio
from pathlib import Path
from urllib.parse import quote
from typing import Annotated

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError

from app.dependencies import CurrentAuth
from app.services.security import secrets_match

from app.services.datasheet_claude import gerar_datasheet_com_claude
from app.services.datasheet_choice import generate_choice_datasheet_full
from app.services.datasheet_portwell import generate_portwell_datasheet_full
from app.services.datasheet_sag import generate_sag_datasheet_full
from app.services.datasheet_validation import validate_analysis
from app.schemas.registration import RegistrationProduct
from app.services.digitalization_storage import approve_draft, create_draft, finalize_draft, load_run, run_file, validate_sku, verify_package
from app.services.registration_package import process_image


router = APIRouter(
    prefix="/api/v1/digitalizacao",
    tags=["digitalizacao"],
)


def _require_authorized(auth: CurrentAuth, csrf_token: str | None) -> None:
    _require_manager(auth)
    if not csrf_token or not secrets_match(auth.login_session.csrf_hash, csrf_token):
        raise HTTPException(status_code=403, detail="Token CSRF inválido.")


def _require_manager(auth: CurrentAuth) -> None:
    if auth.user.role not in {"gestor", "desenvolvedor"}:
        raise HTTPException(status_code=403, detail="Somente gestores podem finalizar digitalizações.")


@router.post("/extrair-especificacoes")
async def extrair_especificacoes(
    codigo: Annotated[str, Form(...)],
    nome: Annotated[str, Form(...)],
    datasheet: Annotated[UploadFile, File(...)],
    auth: CurrentAuth,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
):
    _require_authorized(auth, csrf_token)
    nome = nome.strip()
    try:
        validate_sku(codigo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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

    if len(pdf_bytes) > 30 * 1024 * 1024 or not pdf_bytes.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="PDF inválido ou acima de 30 MiB.")
    try:
        import pymupdf
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
            if document.page_count > 100:
                raise ValueError("PDF excede 100 páginas.")
            extracted_text = "\n".join(page.get_text() for page in document)[:100000]
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=f"Falha ao ler o PDF: {exc}") from exc

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
    auth: CurrentAuth,
    informacoes_adicionais: Annotated[str, Form()] = "",
    configuracao: Annotated[str, Form()] = "",
    opcionais: Annotated[str, Form()] = "",
    nivel: Annotated[str, Form()] = "completo",
    datasheet: Annotated[UploadFile | None, File()] = None,
    imagens: Annotated[list[UploadFile] | None, File()] = None,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
):
    _require_authorized(auth, csrf_token)
    nome = nome.strip()
    empresa = empresa.strip().lower()
    informacoes_adicionais = informacoes_adicionais.strip()

    try:
        validate_sku(codigo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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

    if not informacoes_adicionais and not datasheet and not imagens:
        raise HTTPException(
            status_code=400,
            detail=(
                "Extraia as especificações do PDF ou informe "
                "as especificações manualmente antes da análise."
            ),
        )

    try:
        if nivel not in {"completo", "resumido"}:
            raise ValueError("Nível de datasheet inválido.")
        anexos = {}
        if datasheet:
            content = await datasheet.read(30 * 1024 * 1024 + 1)
            if not content.startswith(b"%PDF-") or len(content) > 30 * 1024 * 1024:
                raise ValueError("Datasheet original inválido ou acima de 30 MiB.")
            anexos[Path(datasheet.filename or "datasheet.pdf").name] = content
        for index, upload in enumerate(imagens or [], 1):
            if index > 20:
                raise ValueError("Limite de 20 fotos por produto.")
            raw = await upload.read(25 * 1024 * 1024 + 1)
            if len(raw) > 25 * 1024 * 1024:
                raise ValueError("Foto acima de 25 MiB.")
            extension = Path(upload.filename or "foto.jpg").suffix.lower()
            if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
                raise ValueError(f"Formato de foto inválido: {extension}.")
            anexos[f"img_{index:02d}{extension}"] = raw
        resultado = await asyncio.to_thread(
            gerar_datasheet_com_claude, empresa, nome, anexos,
            configuracao=configuracao, opcionais=opcionais, nivel=nivel,
            cadastro=informacoes_adicionais, codigo=codigo,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        import anthropic
        if isinstance(exc, anthropic.AuthenticationError):
            raise HTTPException(status_code=401, detail="Chave Anthropic inválida ou sem acesso.") from exc
        if isinstance(exc, anthropic.RateLimitError):
            raise HTTPException(status_code=429, detail="Limite de uso Claude atingido; tente mais tarde.") from exc
        if isinstance(exc, anthropic.APITimeoutError):
            raise HTTPException(status_code=504, detail="A API Claude excedeu o tempo de resposta.") from exc
        if isinstance(exc, anthropic.APIConnectionError):
            raise HTTPException(status_code=503, detail="Não foi possível conectar à API Claude.") from exc
        if isinstance(exc, anthropic.NotFoundError):
            raise HTTPException(status_code=422, detail="Modelo Claude indisponível nesta conta.") from exc
        if isinstance(exc, anthropic.BadRequestError):
            raise HTTPException(status_code=422, detail="Claude rejeitou o modelo ou os anexos; confira a configuração.") from exc
        raise HTTPException(status_code=502, detail="Falha na análise Claude; consulte os logs do servidor.") from exc

    return {
        "success": True,
        "empresa": empresa,
        "codigo": codigo,
        "data": resultado.dados,
        "avisos": resultado.resultado.avisos,
        "pendencias": resultado.resultado.pendencias,
        "conferencia_fontes": resultado.resultado.conferencia_fontes,
        "ciclos": resultado.ciclos,
    }


@router.post("/gerar-datasheet")
async def gerar_datasheet(
    empresa: Annotated[str, Form(...)],
    codigo: Annotated[str, Form(...)],
    analysis_json: Annotated[str, Form(...)],
    auth: CurrentAuth,
    imagens: Annotated[list[UploadFile] | None, File()] = None,
    datasheet: Annotated[UploadFile | None, File()] = None,
    rotations_json: Annotated[str, Form()] = "[]",
    size: Annotated[str, Form()] = "1200",
    quality: Annotated[int, Form()] = 90,
    nome: Annotated[str, Form()] = "",
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
):
    _require_authorized(auth, csrf_token)
    _require_manager(auth)
    empresa = empresa.strip().lower()
    try:
        validate_sku(codigo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if empresa not in {"portwell", "choice", "sag"}:
        raise HTTPException(status_code=400, detail="Empresa inválida.")

    if len(analysis_json) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Análise técnica acima de 2 MiB.")
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
    if not nome.strip():
        raise HTTPException(status_code=422, detail="Nome do produto obrigatório.")
    try:
        validate_analysis(analysis, name=nome.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        rotations = json.loads(rotations_json)
        if not isinstance(rotations, list) or len(rotations) != len(imagens or []):
            raise ValueError("Rotações e imagens não correspondem.")
        actual_size = None if size == "original" else int(size)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    image_bytes: list[bytes] = []
    image_attachments: dict[str, bytes] = {}

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

        try:
            image_bytes.append(process_image(await imagem.read(25 * 1024 * 1024 + 1), rotation=rotations[len(image_bytes)], size=actual_size, quality=quality))
            image_attachments[f"img_{len(image_bytes):02d}{Path(imagem.filename or 'foto.jpg').suffix.lower()}"] = image_bytes[-1]
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=f"Imagem {imagem.filename}: {exc}") from exc

    if datasheet:
        source_pdf = await datasheet.read(30 * 1024 * 1024 + 1)
        if len(source_pdf) > 30 * 1024 * 1024 or not source_pdf.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="PDF original inválido ou acima de 30 MiB.")
        image_attachments[Path(datasheet.filename or "datasheet.pdf").name] = source_pdf
    try:
        validate_analysis(analysis, name=nome.strip(), attachments=set(image_attachments))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        if empresa == "portwell":
            result = generate_portwell_datasheet_full(
                data=analysis,
                anexos=image_attachments,
                codigo=codigo,
            )

        elif empresa == "choice":
            result = generate_choice_datasheet_full(
                data=analysis,
                anexos=image_attachments,
                codigo=codigo,
            )

        else:
            result = generate_sag_datasheet_full(
                data=analysis,
                anexos=image_attachments,
                codigo=codigo,
            )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gerar o datasheet: {exc}",
        ) from exc

    try:
        draft = create_draft(
            empresa, codigo, nome, analysis, image_bytes, result.pdf,
            image_processing={"format": "JPEG", "max_dimension": actual_size, "quality": quality, "rotations": rotations},
            previews=result.previews, warnings=result.avisos,
            pending=result.pendencias, source_check=result.conferencia_fontes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=507, detail=f"Falha ao salvar o datasheet no armazenamento configurado: {exc}") from exc

    filename = f"{codigo}_Datasheet.pdf"

    return Response(
        content=result.pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-PRM-Run-ID": draft["run_id"],
            "X-PRM-Warnings": str(len(result.avisos)),
            "X-PRM-Pendencias": str(len(result.pendencias)),
        },
    )


@router.get("/execucoes/{run_id}")
def get_execution(run_id: str, auth: CurrentAuth):
    _require_manager(auth)
    try:
        record = load_run(run_id)
        return verify_package(run_id) if record.get("status") == "validated" else record
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/execucoes/{run_id}/aprovar")
def approve_execution(
    run_id: str, auth: CurrentAuth,
    acknowledge_pending: Annotated[bool, Form()] = False,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
):
    _require_authorized(auth, csrf_token)
    _require_manager(auth)
    try:
        return approve_draft(run_id, acknowledge_pending=acknowledge_pending)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/execucoes/{run_id}/previas/{index}")
def download_preview(run_id: str, index: int, auth: CurrentAuth):
    _require_manager(auth)
    try:
        record = load_run(run_id)
        if index < 1 or index > record.get("preview_count", 0):
            raise ValueError("Prévia não encontrada.")
        path = run_file(run_id, "datasheet").parent / f"preview_{index}.png"
        if not path.is_file():
            raise ValueError("Prévia não encontrada.")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="image/png")


@router.get("/execucoes/{run_id}/datasheet")
def download_datasheet(run_id: str, auth: CurrentAuth):
    _require_manager(auth)
    try:
        record = load_run(run_id)
        path = run_file(run_id, "datasheet")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="application/pdf", filename=f"{record['sku']}_Datasheet.pdf")


@router.get("/execucoes/{run_id}/fotos/{index}")
def download_processed_image(run_id: str, index: int, auth: CurrentAuth):
    _require_manager(auth)
    try:
        record = load_run(run_id)
        if index < 1 or index > record["image_count"]:
            raise ValueError("Foto não encontrada.")
        path = run_file(run_id, "datasheet").parent / f"image_{index}.jpg"
        if not path.is_file():
            raise ValueError("Foto processada não encontrada.")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="image/jpeg", filename=f"{record['sku']}_foto{index}.jpg")


@router.get("/execucoes/{run_id}/pacote")
def download_package(run_id: str, auth: CurrentAuth):
    _require_manager(auth)
    try:
        record = verify_package(run_id)
        path = run_file(run_id, "package")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="application/zip", filename=f"{record['sku']}.zip")


@router.post("/finalizar")
async def finalize_digitization(
    auth: CurrentAuth,
    run_id: Annotated[str, Form(...)],
    product_json: Annotated[str, Form(...)],
    source_datasheet: Annotated[UploadFile | None, File()] = None,
    drawing_3d: Annotated[UploadFile | None, File()] = None,
    manuals: Annotated[list[UploadFile] | None, File()] = None,
    certificates: Annotated[list[UploadFile] | None, File()] = None,
    other_files: Annotated[list[UploadFile] | None, File()] = None,
    new_version: Annotated[bool, Form()] = False,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
):
    _require_authorized(auth, csrf_token)
    _require_manager(auth)
    try:
        product = RegistrationProduct.model_validate_json(product_json)
        documents = []
        for role, uploads in (
            ("source_datasheet", [source_datasheet] if source_datasheet else []),
            ("drawing_3d", [drawing_3d] if drawing_3d else []),
            ("manual", manuals or []), ("certificate", certificates or []), ("other", other_files or []),
        ):
            for upload in uploads:
                documents.append((role, upload.filename or role, await upload.read(50 * 1024 * 1024 + 1)))
        record = finalize_draft(run_id, product, documents, new_version=new_version)
        verify_package(run_id)
        return {"run_id": run_id, "status": record["status"], "folder_path": record["folder_path"], "package_version": record["package_version"], "manifest": record["manifest"]}
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, ValidationError, OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
