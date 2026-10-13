from types import SimpleNamespace

import pytest

from app.routers.pages import templates
from app.services.refined_catalog_database import group_families, current_comparison, current_items


def test_group_partition_never_counts_unknown_as_shared_or_internal_as_public():
    manifest = {"families": {
        "known": {"public_counts": {"portwell": 1}},
        "internal": {"public_counts": {"choice": 0}, "counts": {"choice": 5}},
        "unknown": {"public_counts": {"choice": 8}},
    }}
    assert group_families(manifest, "shared") == ["known"]
    assert group_families(manifest, "not_found") == ["internal"]
    assert group_families(manifest, "review") == ["unknown"]
    assert group_families(manifest, "") is None


def item(item_id, value="24 V"):
    return {"item_id": item_id, "source_id": "choice", "sku": "A1", "record_key": "1", "title_display": "Fonte",
            "classification": {"family_label": "Fonte"}, "quality_issues": ["test_conflict"],
            "commercial": {"prices": [{"amount": "9999.99", "kind": "regular", "visibility": "internal_only"}]},
            "attribute_observations": [{"attribute_code": "voltage", "raw_name": "Tensão", "raw_value": value,
                                       "configuration_scope": "installed", "unit": "V", "knowledge_state": "conflicting"}]}


def test_comparison_preserves_repeated_conflicting_values_and_scope_and_prices():
    first, second = item("1"), item("2", "12 V")
    first["attribute_observations"].append({**first["attribute_observations"][0], "raw_value": "36 V"})
    second["attribute_observations"].append({**second["attribute_observations"][0], "configuration_scope": "optional"})
    comparison = current_comparison([first, second])
    assert len(comparison["rows"]) == 2
    installed = next(r for r in comparison["rows"] if r["scope"] == "installed")
    assert [v["raw"] for v in installed["values"]["1"]] == ["24 V", "36 V"]
    template = templates.get_template("_current_comparison.html")
    seller = template.render(current_comparison=comparison, user=SimpleNamespace(role="vendedor"))
    manager = template.render(current_comparison=comparison, user=SimpleNamespace(role="gestor"))
    assert "9999.99" not in seller and "9999.99" in manager
    assert "36 V" in seller and "optional" in seller and "conflito" in seller


def test_missing_tenant_snapshot_or_stale_selection_is_not_resolved_from_history(monkeypatch):
    import app.services.refined_catalog_database as service
    monkeypatch.setattr(service, "database_manifest", lambda *args: None)
    with pytest.raises(LookupError):
        current_items(None, "other-organization", [])
    monkeypatch.setattr(service, "database_manifest", lambda *args: {"run_id": "new"})
    with pytest.raises(ValueError, match="mudou"):
        current_items(None, "org", [], run_id="old")
