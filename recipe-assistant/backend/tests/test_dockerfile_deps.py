"""Guard against dependency drift between pyproject.toml and the Dockerfile.

The production image installs backend dependencies via a hardcoded ``pip
install`` list in ``recipe-assistant/Dockerfile`` rather than from
``pyproject.toml``. When the two lists drift, the app imports a package that
exists in dev (installed via ``pip install -e .[dev]``) but is missing in the
container, crashing uvicorn on startup. This test fails loudly if any runtime
dependency declared in pyproject.toml is absent from the Dockerfile.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PYPROJECT = BACKEND_DIR / "pyproject.toml"
DOCKERFILE = BACKEND_DIR.parent / "Dockerfile"


def _dep_name(spec: str) -> str:
    """Extract the bare package name from a requirement spec.

    'uvicorn[standard]>=0.34.0' -> 'uvicorn'
    'reportlab>=4.2.0'          -> 'reportlab'
    """
    return re.split(r"[\[<>=!~ ;]", spec.strip(), maxsplit=1)[0].lower()


def test_pyproject_runtime_deps_are_in_dockerfile():
    data = tomllib.loads(PYPROJECT.read_text())
    runtime_deps = {_dep_name(d) for d in data["project"]["dependencies"]}

    dockerfile_text = DOCKERFILE.read_text().lower()

    missing = sorted(d for d in runtime_deps if d not in dockerfile_text)
    assert not missing, (
        f"Runtime dependencies in pyproject.toml missing from Dockerfile: {missing}. "
        "Add them to the `pip install` block in recipe-assistant/Dockerfile."
    )
