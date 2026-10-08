"""Extração conservadora para revisão; nunca aprova equivalência automaticamente."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


CPU = re.compile(r"\b(?:INTEL|NTEL|LNTEL)[®™\s]*(?:PROCESSADOR\s*)?(?:CORE[®™\s]*)?I([3579])[-\s]?(\d{4,5}[A-Z]{0,3})\b", re.I)
STORAGE = re.compile(r"(?<!\w)(?:(\d+)\s*[X×]\s*)?(\d+(?:[,.]\d+)?)\s*(GB|TB)\s+SSD\b", re.I)
RAM = re.compile(r"(?<!\w)(\d+)\s*GB\s*(?:(DDR\s*[345])\s*)?(SODIMM|SO-DIMM|RAM|MEM[ÓO]RIA)\b", re.I)
RAM_TITLE = re.compile(r"(?<!\w)(\d+)\s*GB\s*(DDR\s*[345])\b", re.I)
USB = re.compile(r"\b(\d+)\s*[X×]\s*USB\s*(\d+(?:\.\d+)?)?\b", re.I)
COM = re.compile(r"\b(\d+)\s*[X×]\s*COM\s*(RS\s*232(?:\s*/\s*422(?:\s*/\s*485)?)?)?", re.I)
VOLTAGE = re.compile(r"(?<!\w)(\d+(?:[,.]\d+)?)\s*V\s*(CC|CA|DC|AC)?\b", re.I)
CURRENT = re.compile(r"(?<!\w)(\d+(?:[,.]\d+)?)\s*A\b(?!\s*C-)", re.I)


@dataclass(frozen=True)
class Assertion:
    key: str
    value: Any
    scope: str
    source_field: str
    evidence: str
    rule: str
    state: str = "known"


@dataclass
class TechnicalAnalysis:
    family: str | None = None
    subtype: str | None = None
    form_factor: str | None = None
    item_role: str = "equipment"
    assertions: list[Assertion] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    def values(self, key: str, scope: str | None = None) -> list[Any]:
        return [item.value for item in self.assertions if item.key == key and (scope is None or item.scope == scope)]


def normalize_cpu(value: str) -> str | None:
    """Typo ntel/lntel só é aceito junto do padrão Core iN-modelo."""
    match = CPU.search(value)
    if not match:
        return None
    return f"Intel Core i{match.group(1)}-{match.group(2).upper()}"


def _append(result: TechnicalAnalysis, key: str, value: Any, scope: str, field_name: str, evidence: str, rule: str) -> None:
    assertion = Assertion(key, value, scope, field_name, evidence, rule)
    if assertion not in result.assertions:
        result.assertions.append(assertion)


def analyze_technical(*, name: str, description: str = "", application: str = "", category: str = "") -> TechnicalAnalysis:
    """Extrai apenas evidência contextual do próprio SKU; legado não vira verdade."""
    result = TechnicalAnalysis()
    title = name.casefold()
    all_text = " ".join((name, description, application)).casefold()
    if re.search(r"\bkit\b", title):
        result.item_role = "kit"
    elif re.search(r"\b(bloco de contato|supressor|bobina para contator|para contator)\b", title):
        result.item_role = "accessory"
    if re.search(r"\b(computador|box pc|panel pc|painel pc|pc fanless)\b", title) and not re.search(r"\b(monitor|ihm)\b", title):
        result.family = "industrial_computer"
        if re.search(r"\bbox pc\b", all_text):
            result.form_factor = "box_pc"
        elif re.search(r"\b(panel pc|painel pc)\b", all_text):
            result.form_factor = "panel_pc"
    elif result.item_role == "kit":
        result.family = "kit"
    elif re.search(r"\bcontator(?:es)?\b", title) and result.item_role != "accessory":
        result.family = "contactor"
        if "seguran" in all_text:
            result.subtype = "safety_claimed"
            result.issues.append("revisar_subtipo_seguranca")
    elif re.search(r"\b(ups|nobreak|fonte)\b", all_text):
        result.family = "power_supply"
        result.subtype = "ups" if re.search(r"\b(ups|nobreak)\b", all_text) else "supply"
    elif re.search(r"\brel[eé]\b", title):
        result.family = "relay"
    if result.family == "contactor" and "rel" in title and "contator" in title:
        result.issues.append("revisar_subtipo_rele_contator")
    if result.family == "contactor" and "sensor" in category.casefold():
        result.issues.append("conflito_categoria_comercial")
    if result.family == "relay" and "seguran" in category.casefold():
        result.issues.append("revisar_funcao_seguranca")
    if result.item_role == "kit":
        for match in re.finditer(r"\b(\d+)\s+POLOS(?:/FASES)?\b", all_text, re.I):
            _append(result, "coverage.monitored_poles", int(match.group(1)), "kit_coverage", "combined", match.group(0), "kit.coverage.v1")
    for field_name, text in (("name", name), ("description", description), ("application", application)):
        if not text:
            continue
        cpu = CPU.search(text)
        if cpu:
            _append(result, "cpu.model", normalize_cpu(cpu.group(0)), "installed_configuration", field_name, cpu.group(0), "cpu.model.v1")
        if result.family == "industrial_computer":
            for match in RAM.finditer(text):
                before = text[max(0, match.start() - 22):match.start()].casefold()
                if re.search(r"(?:at[eé]|m[aá]xim[oa]|suporta)\s*$", before):
                    scope = "platform_maximum"
                else:
                    scope = "installed_configuration"
                _append(result, "memory.capacity_gb", int(match.group(1)), scope, field_name, match.group(0), "memory.scope.v1")
                if match.group(3):
                    _append(result, "memory.form", match.group(3).upper().replace("-", ""), scope, field_name, match.group(0), "memory.form.v1")
                if match.group(2):
                    _append(result, "memory.generation", match.group(2).upper().replace(" ", ""), scope, field_name, match.group(0), "memory.generation.v1")
            if field_name == "name":
                for match in RAM_TITLE.finditer(text):
                    _append(result, "memory.capacity_gb", int(match.group(1)), "installed_configuration", field_name, match.group(0), "memory.title.v1")
                    _append(result, "memory.generation", match.group(2).upper().replace(" ", ""), "installed_configuration", field_name, match.group(0), "memory.title.v1")
            for match in re.finditer(r"(?:at[eé]|m[aá]xim[oa]|suporta\s+at[eé])\s*(\d+)\s*GB", text, re.I):
                _append(result, "memory.capacity_gb", int(match.group(1)), "platform_maximum", field_name, match.group(0), "memory.maximum.v1")
            for match in STORAGE.finditer(text):
                after = text[match.end():match.end()+35]
                form = re.search(r"\b2[,.]5\s*[\"”]", after)
                interface = re.search(r"\b(SATA|NVME)\b", after, re.I)
                value = {"quantity": int(match.group(1) or 1), "capacity": match.group(2).replace(",", "."), "unit": match.group(3).upper(), "interface": interface.group(1).upper() if interface else None, "form_factor_in": "2.5" if form else None}
                _append(result, "storage.devices", value, "installed_configuration", field_name, match.group(0), "storage.devices.v1")
            for match in USB.finditer(text):
                _append(result, "ports.usb", {"quantity": int(match.group(1)), "version": match.group(2)}, "installed_configuration", field_name, match.group(0), "ports.usb.v1")
            for match in COM.finditer(text):
                protocols = ["RS" + part for part in re.findall(r"\d{3}", match.group(2) or "")]
                _append(result, "ports.com", {"quantity": int(match.group(1)), "protocols": protocols}, "installed_configuration", field_name, match.group(0), "ports.com.v1")
            input_match = re.search(r"\bDC-IN\s*(\d+)\s*[~–-]\s*(\d+)\b", text, re.I)
            if input_match:
                _append(result, "power.input_range_vdc", [int(input_match.group(1)), int(input_match.group(2))], "equipment_input", field_name, input_match.group(0), "power.dc_in_context.v1")
            supply_match = re.search(r"FONTE\s+ALIMENTA\S*\s*(\d+)\s*V\b", text, re.I)
            if supply_match:
                _append(result, "power.supply_nominal_v", int(supply_match.group(1)), "included_supply", field_name, supply_match.group(0), "power.included_supply.v1")
        if result.family == "contactor" and result.item_role == "equipment":
            for match in re.finditer(r"\b(\d+)\s*A\s+EM\s+(AC-\d+)\b", text, re.I):
                _append(result, "current.rating_a", {"value": int(match.group(1)), "utilization": match.group(2).upper()}, "power_contacts", field_name, match.group(0), "contactor.current.v1")
            for match in re.finditer(r"\bBOBINA\s*(\d+)\s*V\s*(CC|CA|DC|AC)\b", text, re.I):
                _append(result, "coil.voltage", {"value": int(match.group(1)), "kind": match.group(2).upper()}, "coil", field_name, match.group(0), "contactor.coil.v1")
    return result


def assess_pair(left: TechnicalAnalysis, right: TechnicalAnalysis) -> dict[str, Any]:
    """Decisão conservadora: jamais transforma score lexical em equivalência."""
    blockers: list[str] = []
    if left.item_role != right.item_role:
        blockers.append("papel_do_item_diferente")
    if left.family and right.family and left.family != right.family:
        blockers.append("familia_tecnica_diferente")
    if left.family == right.family == "power_supply" and left.subtype != right.subtype:
        blockers.append("funcao_fonte_ups_diferente")
    if blockers:
        return {"status": "incompativel", "blockers": blockers}
    if left.family == right.family == "contactor":
        left_current, right_current = left.values("current.rating_a"), right.values("current.rating_a")
        if not left_current or not right_current or left_current != right_current:
            return {"status": "dados_insuficientes", "blockers": ["corrente_ou_contexto_nao_confirmado"]}
    return {"status": "candidato_para_revisao" if left.family and right.family else "dados_insuficientes", "blockers": []}
