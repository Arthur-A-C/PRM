"""Indicadores exclusivamente do snapshot oficial da organização.

Distribuição/sobreposição de famílias não é equivalência técnica.
Não há fallback para análises ou ofertas legadas.
"""

from app.services.refined_catalog import ORDER


def summarize_current(manifest):
    if not manifest:
        return {"schema_version": 2, "status": "no_current_snapshot", "run_id": None}
    sources = []
    for source in ORDER:
        counts = manifest["counts"][source]
        sources.append({"code": source, "received": counts["received"], "accepted": counts["accepted"],
                        "public": counts["public_catalog"], "with_attributes": counts["with_attributes"],
                        "unknown_family": counts["unknown_family"], "conflicting_attributes": counts["conflicting_attributes"]})
    reports = []
    for source in ["eco", "dimensional"]:
        total = manifest["counts"][source]["accepted"]
        shared, not_found, unknown = 0, 0, 0
        for family_id, family in manifest["families"].items():
            count = family["counts"].get(source, 0)
            own = family["public_counts"].get("portwell", 0) + family["public_counts"].get("choice", 0)
            if family_id == "unknown":
                unknown += count
            elif own:
                shared += count
            else:
                not_found += count
        if shared + not_found + unknown != total:
            raise ValueError("Distribuição de famílias não reconciliada com snapshot")
        reports.append({"source": source, "total": total, "shared_family": shared,
                        "family_not_found": not_found, "family_pending": unknown,
                        "shared_percent": round(100 * shared / total, 1) if total else 0,
                        "not_found_percent": round(100 * not_found / total, 1) if total else 0,
                        "pending_percent": round(100 * unknown / total, 1) if total else 0})
    return {"schema_version": 2, "status": "published", "run_id": manifest["run_id"],
            "attribute_analysis": manifest.get('attribute_analysis'),
            "created_at": manifest["created_at"], "source_policy": "latest_imports_authoritative",
            "accepted": sum(s["accepted"] for s in sources), "public": sum(s["public"] for s in sources),
            "own_public": sum(s["public"] for s in sources[:2]), "sources": sources, "competitors": reports,
            "technical_status": manifest["matching_status"], "strict_coverage_percent": None}
