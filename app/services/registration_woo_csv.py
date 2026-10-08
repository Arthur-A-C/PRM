"""Header-driven WooCommerce CSV preview/export; never writes to a shop."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

from app.schemas.registration import RegistrationProduct
from app.services.registration_core import fold


ATTRIBUTE_HEADER = re.compile(r"^Nome do atributo (\d+)$")


@dataclass
class WooTemplate:
    headers: list[str]
    rows_by_sku: dict[str, dict[str, str]]
    slots: list[int]
    names: dict[str, tuple[str, bool]]
    ambiguous_globals: set[str]
    padded_rows: int
    budget_meta: str | None
    encoding: str


def parse_woo_export(content: bytes) -> WooTemplate:
    if len(content) > 25 * 1024 * 1024:
        raise ValueError("Export WooCommerce acima de 25 MiB.")
    try:
        decoded = content.decode("utf-8-sig")
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        decoded = content.decode("cp1252")
        encoding = "cp1252"
    reader = csv.reader(io.StringIO(decoded, newline=""), strict=True)
    try:
        headers = next(reader)
    except (StopIteration, csv.Error) as exc:
        raise ValueError("CSV WooCommerce vazio ou inválido.") from exc
    required = {"ID", "Tipo", "SKU", "Nome", "Categorias", "Descrição curta", "Descrição"}
    if not required.issubset(headers) or len(headers) != len(set(headers)):
        raise ValueError("Cabeçalho WooCommerce inválido ou export encapsulado; não use este arquivo para escrever.")
    slots = sorted(int(match.group(1)) for header in headers if (match := ATTRIBUTE_HEADER.fullmatch(header)))
    for slot in slots:
        needed = {f"Valores do atributo {slot}", f"Visibilidade do atributo {slot}", f"Atributo global {slot}"}
        if not needed.issubset(headers):
            raise ValueError(f"Bloco de atributo {slot} incompleto.")
    rows_by_sku = {}
    names = {}
    ambiguous_globals = set()
    budget_meta = "Metadado: _hide_product_price" if "Metadado: _hide_product_price" in headers else None
    malformed = 0
    padded_rows = 0
    for row in reader:
        if len(row) > len(headers):
            malformed += 1
            continue
        if len(row) < len(headers):
            # Some Woo exports concatenate batches with later metadata/attribute
            # columns. CSV omits only trailing empty cells in those earlier rows.
            row += [""] * (len(headers) - len(row))
            padded_rows += 1
        item = dict(zip(headers, row))
        sku = item["SKU"].strip()
        if sku:
            if sku in rows_by_sku:
                raise ValueError(f"SKU duplicado no export: {sku}")
            rows_by_sku[sku] = item
        for slot in slots:
            name = item.get(f"Nome do atributo {slot}", "").strip()
            if name:
                key = fold(name)
                value = (name, item.get(f"Atributo global {slot}", "0") == "1")
                if key in names and names[key][1] != value[1]:
                    ambiguous_globals.add(key)
                else:
                    names.setdefault(key, value)
    if malformed:
        raise ValueError(f"Export tem {malformed} linhas com quantidade incorreta de colunas; correção necessária.")
    return WooTemplate(headers, rows_by_sku, slots, names, ambiguous_globals, padded_rows, budget_meta, encoding)


def _existing_attributes(row: dict[str, str], slots: list[int]) -> list[tuple[str, str, str, str]]:
    result = []
    for slot in slots:
        name = row.get(f"Nome do atributo {slot}", "").strip()
        if name:
            result.append((
                name,
                row.get(f"Valores do atributo {slot}", ""),
                row.get(f"Visibilidade do atributo {slot}", "1"),
                row.get(f"Atributo global {slot}", "0"),
            ))
    return result


def build_woo_row(product: RegistrationProduct, template: WooTemplate, *, approved_fields: set[str] | None = None) -> tuple[dict[str, str], list[str]]:
    old = template.rows_by_sku.get(product.sku)
    row = dict(old) if old else dict.fromkeys(template.headers, "")
    warnings = []
    allowed = approved_fields if approved_fields is not None else {"title", "short_description", "full_description", "categories", "attributes"}
    if not old:
        row["Tipo"] = "simple"
        row["SKU"] = product.sku
        row["Publicado"] = "0"  # Import as draft; never publish implicitly.
        if "Visibilidade no catálogo" in row:
            row["Visibilidade no catálogo"] = "visible"
    if "title" in allowed:
        row["Nome"] = product.commercial_title
    if "short_description" in allowed and product.short_description is not None:
        row["Descrição curta"] = product.short_description
    if "full_description" in allowed and product.full_description is not None:
        row["Descrição"] = product.full_description
    if "categories" in allowed:
        existing = [name.strip() for name in row.get("Categorias", "").split(",") if name.strip()]
        merged = list(existing)
        for path in product.category_paths:
            if fold(path) not in {fold(item) for item in merged}:
                merged.append(path)
        row["Categorias"] = ", ".join(merged)
    if "attributes" in allowed:
        existing = _existing_attributes(row, template.slots)
        original_count = len(existing)
        names = {fold(name) for name, _, _, _ in existing}
        for attribute in product.attributes:
            key = fold(attribute.name)
            if key in names:
                warnings.append(f"Atributo {attribute.name} já existe; valores originais preservados para revisão.")
                continue
            if key in template.ambiguous_globals:
                raise ValueError(f"Atributo {attribute.name} alterna entre global e local no export; selecione a configuração correta antes de incluí-lo.")
            store = template.names.get(key)
            display, global_flag = store if store else (attribute.name, False)
            existing.append((display, ", ".join(attribute.values), "1" if attribute.visible else "0", "1" if global_flag else "0"))
            names.add(key)
        if len(existing) > len(template.slots) or len(existing) > max(15, original_count):
            raise ValueError("Atributos excedem os blocos disponíveis no export; revisão necessária.")
        if old and len(existing) > 15:
            warnings.append("O cadastro existente possui mais de 15 atributos; foram preservados, sem criar novos além do limite.")
        for slot in template.slots:
            for prefix in ("Nome", "Valores", "Visibilidade", "Atributo global"):
                label = f"{prefix} do atributo {slot}" if prefix != "Atributo global" else f"Atributo global {slot}"
                row[label] = ""
        for slot, values in zip(template.slots, existing):
            name, terms, visible, global_flag = values
            row[f"Nome do atributo {slot}"] = name
            row[f"Valores do atributo {slot}"] = terms
            row[f"Visibilidade do atributo {slot}"] = visible
            row[f"Atributo global {slot}"] = global_flag
    # The plugin's budget metadata is preserved for existing rows. For new
    # rows it requires confirmation against the live shop before enabling.
    if not old and template.budget_meta:
        warnings.append("Metadado de orçamento não ativado: confirmar _hide_product_price na loja atual.")
    return row, warnings


def export_woo_csv(product: RegistrationProduct, template: WooTemplate, *, approved_fields: set[str] | None = None) -> tuple[bytes, list[str]]:
    row, warnings = build_woo_row(product, template, approved_fields=approved_fields)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=template.headers, extrasaction="raise", lineterminator="\r\n")
    writer.writeheader()
    writer.writerow(row)
    return output.getvalue().encode("utf-8-sig"), warnings


def export_skus_only(codes: list[str]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(["Código CIGAM"])
    for code in codes:
        writer.writerow([code])
    return output.getvalue().encode("utf-8-sig")
