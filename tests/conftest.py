"""Test bootstrap: make the src-layout package importable without an install.

The harness is dependency-free and not pip-installed during development, so we insert ``src`` on
``sys.path``. Also exposes the repo root and the smoke-fixture path as fixtures.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def smoke_fixture() -> Path:
    return REPO_ROOT / "fixtures" / "harness-smoke"
