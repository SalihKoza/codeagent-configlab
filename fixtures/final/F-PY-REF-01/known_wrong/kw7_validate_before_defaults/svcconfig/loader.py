"""Load a service configuration from raw key/value settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

FIELDS = ("host", "scheme", "port", "timeout", "retries", "tags")


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


def load_config(raw: Mapping[str, object]) -> Config:
    """Build a :class:`Config` from raw settings (for example read from a file or environment).

    ``raw`` maps setting names to values. A setting whose value is ``None`` is treated as omitted.
    ``raw`` itself is never modified. Every problem is reported as :class:`ConfigError` with the
    message shown below.

    Settings:

    - ``host``: a string, otherwise "host must be a string". Surrounding whitespace is removed and
      it is lower-cased. Default ``"localhost"``. Empty after that -> "host must not be empty".
    - ``scheme``: a string, otherwise "scheme must be a string". Surrounding whitespace is removed
      and it is lower-cased. Default ``"http"``. Must then be ``http`` or ``https``, otherwise
      "scheme must be one of: http, https".
    - ``port``: an ``int`` (not ``bool``) or a string of ASCII decimal digits, optionally surrounded
      by whitespace; anything else -> "port must be an integer". Default: ``443`` if the
      (normalized) scheme is ``https``, otherwise ``80``. Must be between 1 and 65535, otherwise
      "port must be between 1 and 65535".
    - ``timeout`` (seconds): an ``int`` or ``float`` (not ``bool``), or a string that ``float()``
      accepts after surrounding whitespace is removed; anything else -> "timeout must be a
      number". Stored as a ``float``. Default ``30.0``. Must be greater than 0 and at most 300,
      otherwise "timeout must be greater than 0 and at most 300".
    - ``retries``: same accepted forms as ``port``; anything else -> "retries must be an
      integer". Default ``3``. Must be between 0 and 10, otherwise "retries must be between 0 and
      10".
    - ``tags``: a comma-separated string, or a list or tuple of strings; anything else -> "tags
      must be a string or a list of strings". Each tag has surrounding whitespace removed and is
      lower-cased; empty tags are dropped and repeated tags are kept only at their first
      position. Stored as a tuple. Default ``()``. At most 5 tags after this normalization,
      otherwise "at most 5 tags allowed".

    Rules between settings, checked after the per-setting rules and in this order:

    1. scheme ``https`` cannot use port 80: "https cannot use port 80".
    2. ``timeout * (retries + 1)`` must not exceed 600: "timeout * (retries + 1) must not exceed
       600".

    A setting name not listed above -> "unknown setting: <name>" (with several unknown names, the
    alphabetically first one is reported).

    When several problems exist, exactly one error is raised, chosen in this order: an unknown
    setting; then a wrong type/form (the "must be a string/an integer/a number/..." messages) in
    setting order host, scheme, port, timeout, retries, tags; then a value outside its allowed
    values or range, in the same setting order; then the rules between settings.
    """
    return Config(**apply_defaults(validate_values(parse_values(raw))))


def parse_values(raw: Mapping[str, object]) -> dict:
    """Check setting names and value forms and coerce numbers; omitted settings stay ``None``."""
    unknown = sorted(k for k in raw if k not in FIELDS)
    if unknown:
        raise ConfigError(f"unknown setting: {unknown[0]}")
    return {"host": _parse_text(raw.get("host"), "host"),
            "scheme": _parse_text(raw.get("scheme"), "scheme"),
            "port": _parse_whole(raw.get("port"), "port"),
            "timeout": _parse_number(raw.get("timeout")),
            "retries": _parse_whole(raw.get("retries"), "retries"),
            "tags": _parse_tags(raw.get("tags"))}


def _parse_text(value, name):
    if value is not None and not isinstance(value, str):
        raise ConfigError(f"{name} must be a string")
    return value


def _parse_whole(value, name):
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text.isascii() and text.isdigit():
            return int(text)
    elif isinstance(value, int) and not isinstance(value, bool):
        return value
    raise ConfigError(f"{name} must be an integer")


def _parse_number(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            pass
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    raise ConfigError("timeout must be a number")


def _parse_tags(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value.split(",")
    if isinstance(value, (list, tuple)) and all(isinstance(t, str) for t in value):
        return list(value)
    raise ConfigError("tags must be a string or a list of strings")


def apply_defaults(values: dict) -> dict:
    """Fill in omitted settings and normalize text values."""
    scheme = "http" if values["scheme"] is None else values["scheme"].strip().lower()
    port = values["port"]
    if port is None:
        port = 443 if scheme == "https" else 80
    tags: list[str] = []
    for tag in values["tags"] or ():
        tag = tag.strip().lower()
        if tag and tag not in tags:
            tags.append(tag)
    return {"host": "localhost" if values["host"] is None else values["host"].strip().lower(),
            "scheme": scheme,
            "port": port,
            "timeout": 30.0 if values["timeout"] is None else values["timeout"],
            "retries": 3 if values["retries"] is None else values["retries"],
            "tags": tuple(tags)}


def validate_values(values: dict) -> dict:
    """Check allowed values and ranges (settings not given are skipped)."""
    host, scheme, port = values["host"], values["scheme"], values["port"]
    timeout, retries, tags = values["timeout"], values["retries"], values["tags"]
    if host is not None and not host:
        raise ConfigError("host must not be empty")
    if scheme is not None and scheme not in ("http", "https"):
        raise ConfigError("scheme must be one of: http, https")
    if port is not None and not 1 <= port <= 65535:
        raise ConfigError("port must be between 1 and 65535")
    if timeout is not None and not 0 < timeout <= 300:
        raise ConfigError("timeout must be greater than 0 and at most 300")
    if retries is not None and not 0 <= retries <= 10:
        raise ConfigError("retries must be between 0 and 10")
    if tags is not None and len(tags) > 5:
        raise ConfigError("at most 5 tags allowed")
    if scheme == "https" and port == 80:
        raise ConfigError("https cannot use port 80")
    if timeout is not None and retries is not None and timeout * (retries + 1) > 600:
        raise ConfigError("timeout * (retries + 1) must not exceed 600")
    return values
