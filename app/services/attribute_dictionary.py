"""Aliases técnicos conservadores; nomes iguais não homologam equivalência."""

import json
import re
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from app.services.catalog_treatment import plain

DICTIONARY = Path(__file__).resolve().parents[2] / "config/catalogs/attributes.json"


def attribute_name(name):
    # ATR_ é um prefixo da representação ECO, não uma característica técnica.
    return plain(re.sub(r"^atr[_\s]+", "", name.strip(), flags=re.I).replace("_", " "))


@lru_cache(maxsize=1)
def load_dictionary():
    return json.loads(DICTIONARY.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def alias_index():
    index = {}
    for entry in load_dictionary()["attributes"]:
        for alias in entry["aliases"]:
            key = attribute_name(alias)
            if key in index and index[key]["code"] != entry["code"]:
                raise ValueError(f"Alias ambíguo: {alias}")
            index[key] = entry
    return index


@lru_cache(maxsize=1)
def canonical_labels():
    labels = {e["code"]: e["label"] for e in load_dictionary()["attributes"]}
    labels.update({"compute.ram": "Memória RAM", "control.memory": "Memória do controlador",
                   "control.memory.work": "Memória de Trabalho"})
    return labels


def normalize_scalar(result):
    """Converter apenas escalares completos; intervalos e alternativas ficam textuais."""
    if result["knowledge_state"] != "known":
        return
    code, value = result["attribute_code"], str(result["normalized_value"])
    if code in {"electrical.poles", "io.digital.input", "io.digital.output", "io.analog.input", "io.analog.output", "io.relay.output"}:
        match = re.fullmatch(r"(\d+)\s*(?:x|polos?|entradas?|saidas?)?", plain(value))
        if match:
            result.update(normalized_value=int(match[1]), value_type="integer")
        return
    units = {}
    if code.startswith("electrical.voltage."):
        units = {"v": ("V", "1"), "kv": ("V", "1000")}
    elif code.startswith("electrical.current."):
        units = {"a": ("A", "1"), "ma": ("A", "0.001")}
    elif code == "electrical.power":
        units = {"w": ("W", "1"), "kw": ("W", "1000")}
    elif code == "electrical.frequency":
        units = {"hz": ("Hz", "1"), "khz": ("Hz", "1000")}
    elif code == "physical.mass":
        units = {"g": ("g", "1"), "kg": ("g", "1000")}
    elif code in {"physical.length", "physical.width", "physical.height", "physical.depth", "physical.diameter", "cable.length"}:
        units = {"mm": ("mm", "1"), "cm": ("mm", "10"), "m": ("mm", "1000")}
    match = re.fullmatch(r"([+-]?\d+(?:[.,]\d+)?)\s*([a-zA-Z]+)", value)
    if match and match[2].lower() in units:
        unit, factor = units[match[2].lower()]
        number = Decimal(match[1].replace(',', '.')) * Decimal(factor)
        result.update(normalized_value=format(number.normalize(), 'f'), value_type="decimal", unit=unit)


def apply_alias(result, name, family):
    label = attribute_name(name)
    entry = alias_index().get(label)
    if entry and not result["mapped"]:
        # IP sem código IP pode ser outro tipo de proteção: não adivinhar.
        if entry["code"] == "protection.ip" and not re.search(r"\bIP[ -]?\d{2}[A-Z]?\b", str(result["normalized_value"]), re.I):
            return result
        result.update(attribute_code=entry["code"], mapped=True)
    if label == "resolucao" and family in {"panel_pc", "hmi"}:
        result.update(attribute_code="display.resolution", mapped=True)
    if label == "memoria de trabalho" and family == "plc":
        result.update(attribute_code="control.memory.work", mapped=True)
    result["canonical_label"] = canonical_labels().get(result["attribute_code"], name)
    if result["mapped"]:
        result["mapping_version"] = load_dictionary()["version"]
        normalize_scalar(result)
    # Quantidades só são extraídas de expressões explícitas e não conflitantes.
    if result["attribute_code"] in {"ports.usb", "ports.serial"} and result["knowledge_state"] == "known":
        value = str(result["normalized_value"])
        token = "USB" if result["attribute_code"] == "ports.usb" else "COM"
        quantities = re.findall(r"\b(\d+)\s*x\s*" + token + r"\b", value, re.I)
        if len(quantities) == 1:
            result["qualifiers"]["explicit_port_count"] = int(quantities[0])
        # Não somar versões/listas alternativas nem contar RS232/422/485 como 3 portas.
        interfaces = set()
        if token == "COM":
            for group in re.findall(r"RS[- ]?((?:232|422|485)(?:\s*/\s*(?:232|422|485))*)", value, re.I):
                interfaces.update("RS-" + part.strip() for part in group.split("/"))
        result["qualifiers"]["interfaces_observed"] = sorted(interfaces)
    if result["attribute_code"] == "protection.ip" and result["knowledge_state"] == "known":
        result["normalized_value"] = re.sub(r"IP[ -]?(\d{2}[A-Z]?)", r"IP\1", str(result["normalized_value"]), flags=re.I).upper()
    return result
