"""Simulação do lote Dimensional em streaming, sem escrita em ofertas publicadas."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from app.services.dimensional_csv import DimensionalCsvAdapter, sha256_file
from app.services.dimensional_semantics import analyze_dimensional


PRIORITY_FAMILIES = {
    "industrial_computer", "power_supply", "contactor", "network_switch",
    "contact_auxiliary", "industrial_cable",
}


def simulate_dimensional(path: Path) -> dict:
    adapter = DimensionalCsvAdapter()
    seen_skus: set[str] = set()
    families: Counter[str] = Counter()
    warnings: Counter[str] = Counter()
    conflicts: Counter[str] = Counter()
    metrics: Counter[str] = Counter()
    cases: dict[str, dict] = {}
    for source in adapter.iter_source_records(path):
        mapped = adapter.map_record(source)
        if mapped.external_code in seen_skus:
            warnings["duplicate_sku"] += 1
        seen_skus.add(mapped.external_code)
        analysis = analyze_dimensional(source)
        families[analysis.family or "unprofiled"] += 1
        warnings.update(mapped.warnings)
        conflicts.update(analysis.conflicts)
        metrics["records"] += 1
        metrics["assertions"] += len(analysis.assertions)
        metrics["specification_media_or_document_candidates_not_downloaded"] += len(analysis.resources)
        if analysis.family in PRIORITY_FAMILIES:
            metrics["priority_family_proposals"] += 1
        if mapped.trusted_stock_quantity is None:
            metrics["trusted_stock_unknown"] += 1
        for assertion in analysis.assertions:
            if assertion.evidence not in source.raw[assertion.source_column]:
                warnings["evidence_not_literal"] += 1
        if mapped.external_code in {"1053629", "197354", "1401334", "1298390", "878767", "1302674", "1302675", "435197", "1267587", "1405472", "355604", "302805", "243665"}:
            cases[mapped.external_code] = {
                "record": source.number,
                "family_proposal": analysis.family,
                "role": analysis.role,
                "form_factor": analysis.form_factor,
                "blocked_fields": analysis.blocked_fields,
                "assertion_count": len(analysis.assertions),
                "warnings": mapped.warnings,
            }
    metrics["distinct_skus"] = len(seen_skus)
    return {
        "mode": "dry_run_staging",
        "source": adapter.source_id,
        "company": adapter.company_code,
        "adapter_version": adapter.version,
        "rules_version": "dimensional.v1",
        "source_sha256": sha256_file(path),
        "metrics": dict(metrics),
        "families": dict(families),
        "warnings": dict(warnings),
        "conflicts": dict(conflicts),
        "cases": cases,
        "published_offers": 0,
        "automatic_equivalences": 0,
    }
