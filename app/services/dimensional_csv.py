"""Adaptador CSV Dimensional v1: leitura incremental e auditoria sem publicação."""

from __future__ import annotations

import csv
import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator


HEADERS = (
    "product_id", "sku", "referencia", "ean", "ncm", "nome", "url", "marca",
    "categoria", "preco", "preco_de", "estoque", "disponibilidade", "descricao_curta",
    "descricao_completa", "especificacoes", "datasheet", "imagem_principal",
    "imagens_galeria", "imagens_local",
)
CASE_SKUS = {
    "1053625", "1053629", "1053630", "1053631", "1053632", "1053633", "1053634",
    "197090", "197354", "238950", "238948", "1272167", "1319162", "1314118",
    "1401334", "1440301", "1440302", "1414941", "1272256", "1197342",
    "1290038", "243665", "84600", "172167", "1290750", "198183",
    "1298390", "878767", "1302674", "1302675", "435197", "1267587",
    "1405472", "355604", "302805", "1184211",
}
SCIENTIFIC = re.compile(r"^[+-]?(?:\d+(?:[,.]\d*)?|[,.]\d+)[Ee][+-]?\d+$")
NCM = re.compile(r"^[0-9]{8}$")
MEDIA_LABELS = {"imagem-360", "relatorio de sustentabilidade", "prefixo 360"}


class DimensionalLayoutError(ValueError):
    pass


@dataclass(frozen=True)
class SourceRecord:
    number: int
    first_physical_line: int
    last_physical_line: int
    raw: dict[str, str]


@dataclass(frozen=True)
class MappedRecord:
    external_code: str
    product_id: str
    seller_code: str
    brand_raw: str
    name_raw: str
    category_raw: str
    price: Decimal | None
    reference_price: Decimal | None
    availability_raw: str
    stock_raw: str
    trusted_stock_quantity: None
    warnings: tuple[str, ...]
    source: SourceRecord


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_gtin(value: str) -> bool:
    if len(value) not in {8, 12, 13, 14} or not value.isascii() or not value.isdecimal():
        return False
    digits = [ord(char) - 48 for char in value]
    weighted = sum(digit * (3 if offset % 2 else 1) for offset, digit in enumerate(reversed(digits[:-1]), 1))
    return (10 - weighted % 10) % 10 == digits[-1]


def parse_announced_price(value: str) -> Decimal | None:
    if not value or not re.fullmatch(r"\d+(?:\.\d+)?", value):
        return None
    try:
        amount = Decimal(value)
    except InvalidOperation:
        return None
    return amount if amount > 0 else None


def specification_pairs(value: str) -> list[tuple[str, str]]:
    """Preserva pares repetidos; não interpreta URL nem fórmula como valor técnico."""
    pairs: list[tuple[str, str]] = []
    for segment in value.split(" | "):
        if ":" not in segment:
            continue
        key, raw_value = segment.split(":", 1)
        key = key.strip().rstrip(":").strip()
        if key:
            pairs.append((key, raw_value.strip()))
    return pairs


class DimensionalCsvAdapter:
    company_code = "dimensional"
    source_id = "dimensional-csv"
    version = "1"
    max_bytes = 512 * 1024 * 1024
    max_field_bytes = 4 * 1024 * 1024

    def detect(self, headers: list[str]) -> dict[str, object]:
        found = set(headers)
        missing = sorted(set(HEADERS) - found)
        return {"compatible": not missing, "missing": missing, "extra": sorted(found - set(HEADERS)), "version": self.version}

    def validate_layout(self, headers: list[str]) -> dict[str, object]:
        diagnosis = self.detect(headers)
        if diagnosis["missing"] or len(headers) != len(set(headers)):
            raise DimensionalLayoutError(f"Colunas obrigatórias ausentes ou duplicadas: {diagnosis['missing']}")
        return diagnosis

    def iter_source_records(self, path: Path) -> Iterator[SourceRecord]:
        if not path.is_file() or path.stat().st_size > self.max_bytes:
            raise DimensionalLayoutError("CSV ausente ou acima do limite de 512 MiB")
        csv.field_size_limit(self.max_field_bytes)
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, dialect="excel", strict=True)
            if reader.fieldnames is None:
                raise DimensionalLayoutError("CSV vazio")
            self.validate_layout(reader.fieldnames)
            previous_line = reader.line_num
            for number, raw in enumerate(reader, 1):
                if None in raw or any(value is None for value in raw.values()):
                    raise DimensionalLayoutError(f"Registro {number}: número de campos incorreto")
                yield SourceRecord(number, previous_line + 1, reader.line_num, raw)
                previous_line = reader.line_num

    def map_record(self, source: SourceRecord) -> MappedRecord:
        raw = source.raw
        sku = raw["sku"]
        if not sku:
            raise DimensionalLayoutError(f"Registro {source.number}: SKU vazio")
        warnings: list[str] = []
        if raw["ean"] and not valid_gtin(raw["ean"]):
            warnings.append("ean_invalido")
        if raw["ncm"] and not NCM.fullmatch(raw["ncm"]):
            warnings.append("ncm_invalido")
        if SCIENTIFIC.fullmatch(raw["referencia"]):
            warnings.append("referencia_cientifica_suspeita")
        if "_xlfn." in raw["especificacoes"]:
            warnings.append("formula_textual_invalida")
        if parse_announced_price(raw["preco"]) is None:
            warnings.append("preco_nao_valido_para_ranking")
        return MappedRecord(
            external_code=sku, product_id=raw["product_id"], seller_code=self.company_code,
            brand_raw=raw["marca"], name_raw=raw["nome"], category_raw=raw["categoria"],
            price=parse_announced_price(raw["preco"]),
            reference_price=parse_announced_price(raw["preco_de"]),
            availability_raw=raw["disponibilidade"], stock_raw=raw["estoque"],
            trusted_stock_quantity=None, warnings=tuple(warnings), source=source,
        )


def audit_dimensional(path: Path) -> dict:
    """Perfila todas as ocorrências; não escreve ofertas nem confia na ficha tratada."""
    adapter = DimensionalCsvAdapter()
    size = path.stat().st_size
    digest = sha256_file(path)
    sku_counts: Counter[str] = Counter()
    product_counts: Counter[str] = Counter()
    ean_counts: Counter[str] = Counter()
    brands: set[str] = set()
    categories: set[str] = set()
    domains: Counter[str] = Counter()
    stock: Counter[str] = Counter()
    availability: Counter[str] = Counter()
    labels: Counter[str] = Counter()
    raw_labels: set[str] = set()
    whole_records: set[str] = set()
    cases: dict[str, dict] = {}
    metrics: Counter[str] = Counter()
    final_line = 1
    for source in adapter.iter_source_records(path):
        raw = source.raw
        final_line = source.last_physical_line
        metrics["records"] += 1
        sku_counts[raw["sku"]] += 1
        product_counts[raw["product_id"]] += 1
        if raw["product_id"] != raw["sku"]:
            metrics["product_id_differs_from_sku"] += 1
        ean = raw["ean"]
        if ean:
            ean_counts[ean] += 1
            if not valid_gtin(ean):
                metrics["ean_invalid"] += 1
        else:
            metrics["ean_empty"] += 1
        if raw["ncm"]:
            if not NCM.fullmatch(raw["ncm"]):
                metrics["ncm_invalid"] += 1
                if raw["ncm"].startswith(("https://", "http://")):
                    metrics["ncm_url"] += 1
        else:
            metrics["ncm_empty"] += 1
        if SCIENTIFIC.fullmatch(raw["referencia"]):
            metrics["reference_scientific"] += 1
        if raw["referencia"] == raw["sku"]:
            metrics["reference_equals_sku"] += 1
        if raw["referencia"] in {"0", "-"}:
            metrics["reference_placeholder"] += 1
        if "_xlfn." in raw["especificacoes"]:
            metrics["formula_in_specifications"] += 1
        if not raw["especificacoes"]:
            metrics["specifications_empty"] += 1
            if not raw["descricao_curta"] and not raw["descricao_completa"]:
                metrics["no_specification_or_descriptions"] += 1
        else:
            pairs = specification_pairs(raw["especificacoes"])
            raw_labels.update(key for key, _ in pairs)
            normalized = [key.casefold().replace("ó", "o") for key, _ in pairs]
            labels.update(normalized)
            if pairs and all(key in MEDIA_LABELS for key in normalized):
                metrics["specifications_media_only"] += 1
        for field, key in (("descricao_curta", "short_description_empty"), ("descricao_completa", "full_description_empty"), ("datasheet", "datasheet_empty"), ("imagens_local", "local_images_empty")):
            if not raw[field]:
                metrics[key] += 1
        brands.add(raw["marca"])
        categories.add(raw["categoria"])
        domains[raw["categoria"].split(">", 1)[0].strip()] += 1
        stock[raw["estoque"]] += 1
        availability[raw["disponibilidade"]] += 1
        price = parse_announced_price(raw["preco"])
        old_price = parse_announced_price(raw["preco_de"])
        if raw["preco"] == raw["preco_de"]:
            metrics["prices_equal_raw"] += 1
        if price is None:
            metrics["price_zero_or_invalid"] += 1
        else:
            metrics["positive_announced_price"] += 1
        if old_price is None:
            metrics["reference_price_zero_or_invalid"] += 1
        if price is not None and old_price is not None:
            metrics["prices_equal" if price == old_price else "price_below_reference" if price < old_price else "price_above_reference"] += 1
        fingerprint = hashlib.sha256(repr(tuple(raw.items())).encode("utf-8")).hexdigest()
        if fingerprint in whole_records:
            metrics["whole_record_duplicates"] += 1
        whole_records.add(fingerprint)
        if raw["sku"] in CASE_SKUS:
            cases[raw["sku"]] = {"record": source.number, "first_physical_line": source.first_physical_line, "last_physical_line": source.last_physical_line, "product_id": raw["product_id"], "ean": ean}
    metrics.setdefault("whole_record_duplicates", 0)
    return {
        "adapter": adapter.source_id, "adapter_version": adapter.version,
        "mode": "read_only_staging", "sha256": digest, "size_bytes": size,
        "headers": list(HEADERS), "header_fields": len(HEADERS), "physical_lines": final_line,
        "metrics": dict(metrics), "distinct_skus": len(sku_counts),
        "duplicate_skus": {key: count for key, count in sku_counts.items() if count > 1},
        "distinct_product_ids": len(product_counts),
        "repeated_product_ids": {key: count for key, count in product_counts.items() if count > 1},
        "ean_shared_groups": sum(count > 1 for count in ean_counts.values()),
        "ean_example_7909492067382": ean_counts["7909492067382"],
        "distinct_brands": len(brands), "distinct_categories": len(categories),
        "distinct_specification_labels": len(raw_labels),
        "distinct_normalized_specification_labels": len(labels), "domains": dict(domains),
        "stock": dict(stock), "availability": dict(availability), "cases": cases,
    }
