"""Locate and load the JSON-Schema contract files under ``schemas/``.

The schemas live at the repository root (``<repo>/schemas``). This resolver walks up from
this file to find that directory, and also honours the ``CONFIGLAB_SCHEMA_DIR`` override so
an installed copy can point elsewhere. Loaded schemas are cached.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

_ENV_OVERRIDE = "CONFIGLAB_SCHEMA_DIR"


def schema_dir() -> Path:
    override = os.environ.get(_ENV_OVERRIDE)
    if override:
        return Path(override)
    # src/codeagent_configlab/_schemas.py -> parents[2] == repo root
    for base in Path(__file__).resolve().parents:
        candidate = base / "schemas"
        if (candidate / "run-manifest.schema.json").exists():
            return candidate
    raise FileNotFoundError("could not locate schemas/ directory (set CONFIGLAB_SCHEMA_DIR)")


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict:
    """Load a schema by file name, e.g. ``"run-manifest.schema.json"``."""
    with open(schema_dir() / name, encoding="utf-8") as fh:
        return json.load(fh)
