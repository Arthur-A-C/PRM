"""Explicit, organization-scoped import into the existing Offer catalog."""
import hashlib
import json
import uuid
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError
from xlrd.biffh import XLRDError
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.dependencies import CurrentAuth, DbSession, AppSettings
from app.models import Company, Offer, CatalogImport, User
from app.services.access import require_management
from app.services.security import secrets_match
from app.services.catalog_origin import resolve_origin, source_group
from app.services.catalog_import import publish_catalog, preview_row
from app.services.catalog_table import FIELDS, read_table, suggest_mapping, mapped_preview

router = APIRouter(prefix="/api/v1/catalog-imports", tags=["Importação de catálogos"])


def guard(auth, token=None, *, write=False):
    require_management(auth.user)
    if write and (not token or not secrets_match(auth.login_session.csrf_hash, token)):
        raise HTTPException(403, "Token CSRF inválido.")


@router.get("/options")
def options(auth: CurrentAuth, db: DbSession, settings: AppSettings):
    guard(auth)
    companies = db.scalars(select(Company).where(Company.organization_id == auth.user.organization_id,
                                                Company.active.is_(True)).order_by(Company.name)).all()
    return {"origins": [{"id": c.id, "name": c.name, "source_group": source_group(c.company_type)} for c in companies],
            "fields": FIELDS, "max_bytes": settings.catalog_upload_mib * 1024 * 1024}


class CompetitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    domain: str | None = Field(default=None, max_length=255)


@router.post("/competitors", status_code=201)
def competitor(payload: CompetitorCreate, auth: CurrentAuth, db: DbSession,
               csrf: str | None = Header(None, alias="X-CSRF-Token")):
    guard(auth, csrf, write=True)
    from app.services.catalog_publication import lock_catalog
    lock_catalog(db, auth.user.organization_id)
    name = payload.name.strip()
    if not name:
        raise HTTPException(422, "Informe o nome do concorrente.")
    existing = db.scalars(select(Company).where(Company.organization_id == auth.user.organization_id)).all()
    if any(c.name.casefold() == name.casefold() for c in existing):
        raise HTTPException(409, "Empresa já cadastrada. Selecione a origem existente.")
    company = Company(id=uuid.uuid4(), organization_id=auth.user.organization_id,
                      code="competitor-" + uuid.uuid4().hex, name=name,
                      domain=payload.domain, company_type="concorrente", active=True)
    db.add(company); db.commit()
    return {"id": company.id, "name": company.name, "source_group": "competitor"}


@router.get('/publication')
def publication_info(auth: CurrentAuth, db: DbSession):
    guard(auth)
    from app.services.catalog_publication import publication_status
    return publication_status(db, auth.user.organization_id)


class PublicationInput(BaseModel):
    version: str = Field(min_length=64, max_length=64)


@router.post('/publication/preview')
def publication_preview(auth: CurrentAuth, db: DbSession,
                        csrf: str | None = Header(None, alias='X-CSRF-Token')):
    guard(auth, csrf, write=True)
    from app.services.catalog_publication import capture, build_snapshot
    data, version = capture(db, auth.user.organization_id)
    try:
        manifest, _, _ = build_snapshot(data, auth.user.organization_id, auth.user.id, version)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    audit = manifest['audit']
    return {'version': version, 'counts': manifest['counts'], 'sources': manifest['source_registry'],
            'audit': audit, 'families': manifest['families'],
            'can_publish': bool(audit['internal_count'] and audit['competitor_count'])}


@router.post('/publication')
def publication_confirm(payload: PublicationInput, auth: CurrentAuth, db: DbSession,
                        csrf: str | None = Header(None, alias='X-CSRF-Token')):
    guard(auth, csrf, write=True)
    from app.services.catalog_publication import publish_registered
    try:
        manifest = publish_registered(db, auth.user.organization_id, auth.user.id, payload.version, auth.user.name)
        db.commit()
        return {'run_id': manifest['run_id'], 'audit': manifest['audit']}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get("/template.csv")
def template(auth: CurrentAuth):
    guard(auth)
    return Response("\ufeffSKU;Nome;Marca;Categoria;Segmento;Preco;Disponibilidade;Descricao\r\n",
                    media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="modelo-catalogo.csv"'})


@router.get("/history")
def history(auth: CurrentAuth, db: DbSession):
    guard(auth)
    rows = db.execute(select(CatalogImport, Company, User.name).join(Company, Company.id == CatalogImport.company_id)
                      .outerjoin(User, User.id == CatalogImport.created_by_id)
                      .where(CatalogImport.organization_id == auth.user.organization_id,
                             Company.organization_id == auth.user.organization_id)
                      .order_by(CatalogImport.created_at.desc()).limit(100)).all()
    return {"items": [{"id": b.id, "source_group": b.mapping.get("_origin", {}).get("source_group", source_group(c.company_type)),
                       "origin": b.mapping.get("_origin", {}).get("name", c.name), "filename": b.original_filename,
                       "user": user, "date": b.created_at, "status": b.status, "new": b.inserted_count,
                       "updated": b.updated_count, "unchanged": b.unchanged_count, "errors": b.rejected_count}
                      for b, c, user in rows]}


@router.post("/prepare")
def prepare(auth: CurrentAuth, db: DbSession, settings: AppSettings,
            file: UploadFile = File(...), company_id: uuid.UUID = Form(...),
            group: Literal["internal", "competitor"] = Form(...),
            sheet: str = Form(""), header_row: int = Form(1), mapping: str = Form("{}"),
            mode: Literal["upsert", "add_only", "update_only"] = Form("upsert"),
            action: Literal["inspect", "preview", "import"] = Form("inspect"),
            expected_preview: str = Form(""), csrf: str | None = Header(None, alias="X-CSRF-Token")):
    guard(auth, csrf, write=True)
    try:
        if action == 'import':
            from app.services.catalog_publication import lock_catalog
            lock_catalog(db, auth.user.organization_id)
        company = resolve_origin(db, auth.user.organization_id, company_id, group, lock=action == "import")
        filename = (file.filename or "").replace("\\", "/").split("/")[-1]
        if not filename or len(filename) > 255 or Path(filename).suffix.lower() not in {".csv", ".xls", ".xlsx"}:
            raise ValueError("Envie CSV, XLSX ou XLS com nome de até 255 caracteres.")
        # TemporaryDirectory cleans uploads after success, parse errors and transaction failures.
        with TemporaryDirectory(prefix="prm-catalog-") as temp:
            path = Path(temp) / ("catalog" + Path(filename).suffix.lower())
            size = 0
            with path.open("wb") as output:
                while chunk := file.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings.catalog_upload_mib * 1024 * 1024:
                        raise ValueError(f"Arquivo acima do limite de {settings.catalog_upload_mib} MiB.")
                    output.write(chunk)
            table = read_table(path, sheet=sheet, header_row=header_row, max_rows=settings.max_import_rows)
            if action == "inspect":
                return {"sheets": table["sheets"], "sheet": table["sheet"], "headers": table["headers"],
                        "sample": table["rows"][:5], "mapping": suggest_mapping(table["headers"])}
            if not table["headers"]:
                raise ValueError("Selecione uma aba.")
            columns = json.loads(mapping)
            if not isinstance(columns, dict):
                raise ValueError("Mapeamento inválido.")
            preview = mapped_preview(path, company.code, table, columns, header_row)
            existing = dict(db.execute(select(Offer.external_code, Offer.source_fingerprint).where(
                Offer.company_id == company.id, Offer.organization_id == auth.user.organization_id)).all())
            signature = hashlib.sha256(json.dumps([str(company.id), group, preview.file_sha256, table["sheet"],
                header_row, columns, mode, existing], sort_keys=True).encode()).hexdigest()
            counts = {"new": 0, "updated": 0, "unchanged": 0, "errors": preview.rejected_rows}
            for row in preview.rows:
                if row.errors:
                    continue
                old = existing.get(row.external_code)
                if (old is not None and mode == "add_only") or (old is None and mode == "update_only") or old == row.fingerprint:
                    counts["unchanged"] += 1
                else:
                    counts["updated" if old is not None else "new"] += 1
            result = {"source_group": group, "origin": company.name, "filename": filename,
                      "counts": counts, "sample": [preview_row(r) for r in preview.rows[:20]],
                      "errors": [preview_row(r) for r in preview.rows if r.errors][:100], "preview_token": signature}
            if action == "preview":
                return result
            if not expected_preview or expected_preview != signature:
                raise HTTPException(409, "Dados ou opções mudaram. Gere uma nova prévia antes de importar.")
            if not preview.valid_rows:
                raise ValueError("Nenhuma linha válida para importar.")
            preview.path = Path(filename)
            published = publish_catalog(db, preview, company, created_by_id=auth.user.id, mode=mode)
            db.flush()
            batch = db.get(CatalogImport, published.import_id)
            if not published.idempotent:
                batch.source_path = "upload://" + filename
                batch.mapping = {**columns, "_mode": mode,
                                 "_origin": {"source_group": group, "name": company.name, "id": str(company.id)}}
            db.commit()
            return {**result, "result": asdict(published), "catalog_url": "/catalogos?view=legacy&company=" + company.code}
    except LookupError as exc:
        db.rollback()
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, UnicodeError, OSError, KeyError, BadZipFile, ParseError, XLRDError) as exc:
        db.rollback()
        raise HTTPException(422, "Arquivo ou configuração inválida: " + str(exc)) from exc
    finally:
        file.file.close()
