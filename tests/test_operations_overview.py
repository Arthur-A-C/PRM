"""Read-only operations overview: persisted facts only, no paths or analysis exposed."""
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.operations_overview import operations_overview


def write_run(root, run_id, **record):
    folder = root / "_runs" / run_id
    folder.mkdir(parents=True)
    base = {"run_id": run_id, "status": "draft", "company": "choice", "sku": "CH-001", "name": "Produto",
            "analysis": {"segredo": "não expor"}, "created_at": "2026-10-10T12:00:00+00:00", "image_count": 2,
            "warnings": [], "pending": []}
    base.update(record)
    (folder / "record.json").write_text(json.dumps(base), encoding="utf-8")


def test_missing_storage_reports_no_runs(tmp_path):
    result = operations_overview(tmp_path)
    assert result["status"] == "no_runs" and result["items"] == []
    assert result["untracked_stages"] == ["csv", "woocommerce"] and result["failures_tracked"] is False


def test_reads_lifecycle_without_exposing_paths_or_analysis(tmp_path):
    write_run(tmp_path, "a" * 32, pending=["foto"], warnings=["aviso"])
    write_run(tmp_path, "b" * 32, status="approved", company="portwell", approved_at="2026-10-11T09:00:00+00:00")
    write_run(tmp_path, "c" * 32, status="validated", company="sag", folder_path="C:/segredo/SAG-1",
              approved_at="2026-10-11T10:00:00+00:00", package_version=2,
              manifest={"generated_at": "2026-10-12T08:30:00+00:00", "product": {"x": 1}})
    write_run(tmp_path, "d" * 32, company="desconhecida")
    (tmp_path / "_runs" / ("e" * 32)).mkdir()
    (tmp_path / "_runs" / "nao-e-execucao").mkdir()
    result = operations_overview(tmp_path)
    assert result["status"] == "ok" and result["unreadable"] == 2
    by_id = {item["run_id"][0]: item for item in result["items"]}
    assert set(by_id) == {"a", "b", "c"}
    assert by_id["a"]["pending"] == 1 and by_id["a"]["warnings"] == 1 and by_id["a"]["validated_at"] is None
    assert by_id["b"]["approved_at"].startswith("2026-10-11T09")
    assert by_id["c"]["validated_at"].startswith("2026-10-12T08:30") and by_id["c"]["package_version"] == 2
    serialized = json.dumps(result)
    assert "segredo" not in serialized and "folder_path" not in serialized and "analysis" not in serialized


def test_endpoint_is_manager_only(monkeypatch):
    from app.routers import operations
    with pytest.raises(HTTPException) as denied:
        operations.overview(SimpleNamespace(user=SimpleNamespace(role="vendedor")))
    assert denied.value.status_code == 403
    monkeypatch.setattr(operations, "operations_overview", lambda: {"status": "no_runs", "items": []})
    assert operations.overview(SimpleNamespace(user=SimpleNamespace(role="gestor")))["status"] == "no_runs"
