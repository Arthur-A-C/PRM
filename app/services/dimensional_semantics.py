"""Propostas técnicas Dimensional com evidência e conflitos, sem publicação."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app.services.dimensional_csv import SourceRecord, specification_pairs, valid_gtin


def fold(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char)).casefold()


@dataclass(frozen=True)
class Assertion:
    attribute: str
    value: Any
    source_column: str
    evidence: str
    scope: str = "offered_variant"
    state: str = "known"
    rule_id: str = "dimensional.v1"


@dataclass
class Analysis:
    sku: str
    family: str | None = None
    role: str = "equipment"
    form_factor: str | None = None
    assertions: list[Assertion] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    blocked_fields: list[str] = field(default_factory=list)
    resources: list[dict[str, str]] = field(default_factory=list)

    def values(self, attribute: str, source_column: str | None = None) -> list[Any]:
        return [item.value for item in self.assertions if item.attribute == attribute and item.state == "known" and (source_column is None or item.source_column == source_column)]

    def add(self, attribute: str, value: Any, column: str, evidence: str, *, scope: str = "offered_variant", state: str = "known") -> None:
        assertion = Assertion(attribute, value, column, evidence, scope, state)
        if assertion not in self.assertions:
            self.assertions.append(assertion)

    def conflict(self, key: str) -> None:
        if key not in self.conflicts:
            self.conflicts.append(key)
        if key not in self.blocked_fields:
            self.blocked_fields.append(key)


def _first_number(text: str, pattern: str) -> tuple[int, str] | None:
    match = re.search(pattern, text, re.I)
    return (int(match.group(1)), match.group(0)) if match else None


def analyze_dimensional(source: SourceRecord) -> Analysis:
    raw = source.raw
    title = raw["nome"]
    title_fold = fold(title)
    short = raw["descricao_curta"]
    full = raw["descricao_completa"]
    specs = specification_pairs(raw["especificacoes"])
    result = Analysis(raw["sku"])

    if "bloco contato auxiliar" in title_fold or "bloco de contato auxiliar" in title_fold:
        result.family, result.role = "contact_auxiliary", "accessory"
    elif "computador" in title_fold and "industrial" in fold(full + " " + title):
        result.family = "industrial_computer"
        if re.search(r"MONTAGEM:\s*PAINEL", full, re.I) and re.search(r"DISPLAY:\s*\d", full, re.I):
            result.form_factor = "panel_pc"
        elif "box pc" in fold(full + " " + title):
            result.form_factor = "box_pc"
    elif "painel operacao" in title_fold:
        result.family = "operator_panel"
    elif "switch" in title_fold:
        result.family = "network_switch"
    elif "contator" in title_fold or ("contato para comutacao" in title_fold and "contator" in fold(short + " " + full)):
        result.family = "contactor"
    elif "fonte" in title_fold or "alimentacao de corrente sitop" in title_fold:
        result.family = "power_supply"
    elif "cabo" in title_fold:
        result.family = "industrial_cable"
    elif "sapato de seguranca" in title_fold:
        result.family = "safety_shoe"

    if raw["ean"] and not valid_gtin(raw["ean"]):
        result.add("ean", raw["ean"], "ean", raw["ean"], state="invalid")
    ncm = raw["ncm"]
    if ncm.startswith(("https://", "http://")):
        result.add("ncm", ncm, "ncm", ncm, state="invalid")
        result.resources.append({"kind": "document_candidate", "url": ncm, "source_column": "ncm"})
    elif ncm and re.fullmatch(r"\d{8}(?:,\s*\d{8})+", ncm):
        codes = [item.strip() for item in ncm.split(",")]
        if len(set(codes)) == 1:
            result.add("ncm_declared", codes[0], "ncm", ncm, scope="source_declared")
        else:
            result.conflict("ncm_declared")

    spec_by_key: dict[str, list[tuple[str, str]]] = {}
    for key, value in specs:
        normalized = fold(key)
        spec_by_key.setdefault(normalized, []).append((value, f"{key}: {value}"))
        if normalized in {"imagem-360", "relatorio de sustentabilidade", "prefixo 360"}:
            result.resources.append({"kind": "media_or_report", "url": value, "source_column": "especificacoes"})
        if "_xlfn." in value:
            result.add(normalized, value, "especificacoes", f"{key}: {value}", state="invalid")

    if result.family == "safety_shoe":
        title_size = _first_number(title, r"\b(3[5-9]|4[0-8])\s*$")
        if title_size:
            result.add("shoe.size", title_size[0], "nome", title_size[1])
        for value, evidence in spec_by_key.get("tamanho", []):
            if value.isdecimal():
                result.add("shoe.size", int(value), "especificacoes", evidence, scope="product_page")
        if len(set(result.values("shoe.size"))) > 1:
            result.conflict("shoe.size")
    if "fita isolante" in title_fold:
        title_reference = re.search(r"\bHB[0-9A-Z]{9}\b", title, re.I)
        if title_reference and raw["referencia"] and title_reference.group(0).upper() != raw["referencia"].upper():
            result.add("manufacturer_part_candidate", title_reference.group(0), "nome", title_reference.group(0))
            result.add("manufacturer_part_candidate", raw["referencia"], "referencia", raw["referencia"], scope="source_declared")
            result.conflict("manufacturer_part_candidate")
        title_length = _first_number(title, r"\b\d+\s*MM\s*[X×]\s*(\d+)\s*M\b")
        if title_length:
            result.add("tape.length_m", title_length[0], "nome", title_length[1])
        for value, evidence in spec_by_key.get("comprimento", []):
            length = _first_number(value, r"\b(\d+)\s*M\b")
            if length:
                result.add("tape.length_m", length[0], "especificacoes", evidence, scope="product_page")
        if len(set(result.values("tape.length_m"))) > 1:
            result.conflict("tape.length_m")
        title_voltage = _first_number(title, r"\b(\d{3,4})\s*V\b")
        if title_voltage:
            result.add("tape.rating_v", title_voltage[0], "nome", title_voltage[1])
        for value, evidence in spec_by_key.get("aplicacao", []):
            voltage = _first_number(value, r"\b(\d{3,4})\s*V\b")
            if voltage:
                result.add("tape.rating_v", voltage[0], "especificacoes", evidence, scope="product_page")
        if len(set(result.values("tape.rating_v"))) > 1:
            result.conflict("tape.rating_v")

    if result.family == "industrial_computer":
        for attribute, pattern, column in (
            ("memory.installed_gb", r"MEMORIA RAM:\s*(\d+)\s*GB\b", "descricao_completa"),
            ("display.diagonal_in", r"DISPLAY:\s*(\d+)\s*[\"”]", "descricao_completa"),
            ("power.input_vdc", r"TENSAO ALIMENTACAO:\s*(\d+)\s*VCC\b", "descricao_completa"),
        ):
            match = re.search(pattern, full, re.I)
            if match:
                result.add(attribute, int(match.group(1)), column, match.group(0))
        if re.search(r"SISTEMA OPERACIONAL:\s*SEM SISTEMA OPERACIONAL", full, re.I):
            result.add("os.included", False, "descricao_completa", "SISTEMA OPERACIONAL: SEM SISTEMA OPERACIONAL")
        part = re.search(r"REFERENCIA:\s*([A-Z0-9]{10,})\b", full, re.I)
        if part:
            result.add("manufacturer_part_candidate", part.group(1), "descricao_completa", part.group(0))

    if result.family == "power_supply":
        for column in ("descricao_curta", "descricao_completa"):
            match = re.search(r"Tens[aã]o de entrada:\s*(\d+)\s*[-–]\s*(\d+)\s*V\s*AC", raw[column], re.I)
            if match:
                result.add("power.input_range_vac", [int(match.group(1)), int(match.group(2))], column, match.group(0))
        # 'ininterrupta' é adjetivo; não transforma a função em UPS.

    if result.family == "contactor":
        for column, text in (("nome", title), ("descricao_curta", short), ("especificacoes", raw["especificacoes"])):
            for match in re.finditer(r"(?:BOBINA(?:\s+EM|\s+DO\s+CIRCUITO\s+DE\s+COMANDO|\s*:\s*)|Tens[aã]o\s+(?:Bobina|Controle):\s*)(\d+)\s*V\s*(CC|CA|DC|AC)?\b", text, re.I):
                result.add("coil.voltage", {"value": int(match.group(1)), "kind": (match.group(2) or "unknown").upper()}, column, match.group(0))
        if len({str(value) for value in result.values("coil.voltage")}) > 1:
            result.conflict("coil.voltage")

    if result.family == "network_switch":
        switch_texts = (("nome", title), ("descricao_curta", short), ("descricao_completa", full))
        negative = next(((column, match) for column, text in switch_texts if (match := re.search(r"n[aã]o\s+gerenci[aá]vel", text, re.I))), None)
        positive = next(((column, match) for column, text in switch_texts if (match := re.search(r"\bgerenci[aá]vel\b", text, re.I)) and not re.search(r"n[aã]o\s+gerenci[aá]vel", text, re.I)), None)
        if negative:
            result.add("switch.managed", False, negative[0], negative[1].group(0))
        elif positive:
            result.add("switch.managed", True, positive[0], positive[1].group(0))
        for column, text, pattern in (
            ("descricao_curta", short, r"MODELO:\s*([^|]+)"),
            ("especificacoes", raw["especificacoes"], r"(?:^|\|\s*)Tipo:\s*([^|]+)"),
        ):
            match = re.search(pattern, text, re.I)
            if match and "SCALANCE" in match.group(1).upper():
                result.add("switch.platform_model", match.group(1).strip(), column, match.group(0).strip())
        if len({fold(value) for value in result.values("switch.platform_model")}) > 1:
            result.conflict("switch.platform_model")
        port = _first_number(short, r"QUANTIDADE PORTAS:\s*(\d+)\s*PORTAS")
        if port:
            result.add("switch.ports_declared", port[0], "descricao_curta", port[1])
        for value, evidence in spec_by_key.get("portas eletricas rj45", []):
            if value.isdecimal():
                result.add("switch.rj45_declared", int(value), "especificacoes", evidence)
        for value, evidence in spec_by_key.get("velocidade", []):
            match = re.search(r"\b(\d+)\s*portas\s*RJ45", value, re.I)
            if match:
                result.add("switch.rj45_declared", int(match.group(1)), "especificacoes", evidence)
        if len(set(result.values("switch.rj45_declared"))) > 1:
            result.conflict("switch.rj45_declared")
        title_ports = _first_number(title, r"\b(\d+)\s*Portas\s*RJ45\b")
        if title_ports:
            result.add("switch.rj45_declared", title_ports[0], "nome", title_ports[1])
        for column, text in switch_texts:
            for match in re.finditer(r"\b(\d+)\s*/\s*(\d+)\s*Mbit/s\b", text, re.I):
                result.add("switch.ethernet_speeds_mbps", [int(match.group(1)), int(match.group(2))], column, match.group(0))

    if result.family == "industrial_cable":
        if "fibra" in fold(raw["especificacoes"]):
            result.add("cable.medium", "optical_fiber", "especificacoes", raw["especificacoes"][:120])
        for value, evidence in spec_by_key.get("secao transversal (bitola)", []):
            if re.search(r"\bmm\s*$", value, re.I) and not re.search(r"mm\s*(?:2|²)", value, re.I):
                result.add("cable.dimension_declared", value, "especificacoes", evidence, scope="unresolved_dimension")
                result.conflict("cable.cross_section")
            elif "µm" in value or "μm" in value:
                result.add("cable.optical_dimension_declared", value, "especificacoes", evidence, scope="optical_medium")
    return result
