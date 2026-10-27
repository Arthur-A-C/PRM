import shutil
import subprocess
from pathlib import Path
import pytest


def test_registration_ui_has_no_legacy_authorization_wording():
    """Normal registration is role-based: the page never mentions staging, homologation, grants or CLI releases."""
    root = Path(__file__).resolve().parents[1]
    template = (root / "app/templates/store_registration.html").read_text(encoding="utf-8")
    script = (root / "app/static/js/store-registration.js").read_text(encoding="utf-8")
    assert "<span>Enviar aprovados</span>" in template
    for text in (template, script):
        lowered = text.lower()
        for legacy in ("staging", "homolog", "grant", "whitelist", "liberação de uso único", "linha de comando"):
            assert legacy not in lowered, legacy


def test_registration_ui_contracts():
    node=shutil.which("node")
    if not node: pytest.skip("Node is a development/CI tool, not a runtime dependency")
    result=subprocess.run([node,"--test","tests/js/store-registration.test.cjs"],
                          cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
