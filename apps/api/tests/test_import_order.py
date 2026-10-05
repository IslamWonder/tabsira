"""The processes that import the code in another order than the API must still start."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("module", ["src.worker", "src.cli.scan_worker", "src.main"])
def test_each_entry_point_imports_in_a_fresh_interpreter(module: str) -> None:
    # A fresh interpreter: inside the test process the modules are already loaded in
    # the API's order, which hides an import ring the scan worker runs into first.
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr[-2000:]
