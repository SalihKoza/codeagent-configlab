"""Configuration value and error types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

class ConfigError(ValueError):
    """Raised for invalid settings. ``str(error)`` is the documented message."""


@dataclass(frozen=True)
class Config:
    """A loaded, validated service configuration (immutable)."""

    host: str
    scheme: str
    port: int
    timeout: float
    retries: int
    tags: tuple[str, ...]
