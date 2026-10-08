"""Pure, conservative normalization of registration-sheet data."""

from __future__ import annotations

import re
import unicodedata

from app.schemas.registration import ProductAttribute, RegistrationProduct


AUXILIARY_FIELDS = {"observacoes", "materiais disponiveis link"}
NAME_ALIASES = {
    "tensao": "Alimentação",
    "tensao de operacao": "Alimentação",
    "tensao de alimentacao": "Alimentação",
    "frequencia": "Frequência",
    "area de atuacao": "Área de Atuação",
    "saidas a rele": "Saídas a Rele",
    "quantidade de botoes": "Quantidade de Botões",
}


def fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return " ".join(
        "".join(char for char in normalized if not unicodedata.combining(char))
        .casefold().replace("_", " ").split()
    )


def category_levels(path: str) -> list[str]:
    parts = [part.strip() for part in path.split(">") if part.strip()]
    return [" > ".join(parts[:index]) for index in range(1, len(parts) + 1)]


def split_terms(value: str, *, multivalued: bool = False) -> list[str]:
    value = value.strip()
    if not value or value == "-":
        return []
    if not multivalued:
        return [value]
    # Preserve decimal comma before splitting declared multivalue terms.
    placeholder = "\u241f"
    protected = re.sub(r"(?<=\d),(?=\d)", placeholder, value)
    return [part.strip().replace(placeholder, ",") for part in protected.split(",") if part.strip()]


def normalize_attributes(
    raw: dict[str, str], *, store_names: dict[str, str] | None = None,
    multivalued: set[str] | None = None,
) -> tuple[list[ProductAttribute], list[str]]:
    """No fabricated globals; ambiguous store aliases must be reviewed."""
    canonical = store_names or {}
    multivalued = multivalued or set()
    result: dict[str, ProductAttribute] = {}
    warnings: list[str] = []
    for name, value in raw.items():
        key = fold(name)
        if key in AUXILIARY_FIELDS:
            continue
        values = split_terms(str(value or ""), multivalued=key in multivalued)
        if not values:
            continue
        display = canonical.get(key) or NAME_ALIASES.get(key) or name.strip()
        identity = fold(display)
        if identity == "classificacao" and ("tipo" in result or "tipo" in canonical):
            warnings.append("Tipo/Classificação requer revisão de identidade do atributo na loja.")
            continue
        if identity in result:
            for item in values:
                if item not in result[identity].values:
                    result[identity].values.append(item)
            warnings.append(f"Atributo duplicado consolidado: {name}")
            continue
        result[identity] = ProductAttribute(name=display, values=values)
    ordered = sorted(result.values(), key=lambda item: (fold(item.name) != "tipo", fold(item.name)))
    if len(ordered) > 15:
        warnings.append("Atributos acima do limite de 15: " + ", ".join(item.name for item in ordered[15:]))
    return ordered[:15], warnings


def from_sheet_row(
    company: str, row: dict[str, str], category: str,
    *, store_names: dict[str, str] | None = None,
) -> RegistrationProduct:
    by_name = {fold(name): value for name, value in row.items()}
    sku = str(by_name.get("codigo cigam") or "").strip()
    technical = str(by_name.get("nome do produto") or "").strip()
    commercial = str(by_name.get("titulo") or "").strip()
    if not sku or not technical or not commercial:
        raise ValueError("Código CIGAM, Nome do Produto e Título são obrigatórios.")
    status_key = next((index for index, name in enumerate(row) if fold(name) == "status"), None)
    if status_key is None:
        raise ValueError("A coluna Status é obrigatória.")
    raw_attributes = {
        name: value for index, (name, value) in enumerate(row.items())
        if index > status_key and fold(name) not in AUXILIARY_FIELDS
    }
    attributes, warnings = normalize_attributes(raw_attributes, store_names=store_names)
    path = category.split("|", 1)[0].strip()
    return RegistrationProduct(
        company=company, cigam_code=sku, sku=sku,
        technical_name=technical, commercial_title=commercial,
        supplier=str(by_name.get("fornecedor") or "").strip() or None,
        category_paths=category_levels(path),
        attributes=attributes, warnings=warnings,
        validation_status="needs_review" if warnings else "draft",
    )
