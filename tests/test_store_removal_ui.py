"""Run browser-independent UI regressions where Node is available; never a runtime dependency."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_removal_ui_contracts():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node available on development/CI host, not required in runtime image")
    result = subprocess.run([node, "--test", "tests/js/store-file-removal.test.cjs"],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
