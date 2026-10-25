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
    return validate_values(apply_defaults(parse_values(raw)))


def parse_values(raw):
    return raw


def apply_defaults(values):
    return values


def validate_values(raw):
    unknown = sorted(k for k in raw if k not in FIELDS)
    if unknown:
        raise ConfigError(f"unknown setting: {unknown[0]}")

    # -- parse / coerce ---------------------------------------------------------------------
    host = raw.get("host")
    if host is not None and not isinstance(host, str):
        raise ConfigError("host must be a string")

    scheme = raw.get("scheme")
    if scheme is not None and not isinstance(scheme, str):
        raise ConfigError("scheme must be a string")

    port = raw.get("port")
    if port is not None:
        if isinstance(port, bool):
            raise ConfigError("port must be an integer")
        if isinstance(port, str):
            text = port.strip()
            if not (text.isascii() and text.isdigit()):
                raise ConfigError("port must be an integer")
            port = int(text)
        elif not isinstance(port, int):
            raise ConfigError("port must be an integer")

    timeout = raw.get("timeout")
    if timeout is not None:
        if isinstance(timeout, bool):
            raise ConfigError("timeout must be a number")
        if isinstance(timeout, str):
            try:
                timeout = float(timeout.strip())
            except ValueError:
                raise ConfigError("timeout must be a number") from None
        elif isinstance(timeout, (int, float)):
            timeout = float(timeout)
        else:
            raise ConfigError("timeout must be a number")

    retries = raw.get("retries")
    if retries is not None:
        if isinstance(retries, bool):
            raise ConfigError("retries must be an integer")
        if isinstance(retries, str):
            text = retries.strip()
            if not (text.isascii() and text.isdigit()):
                raise ConfigError("retries must be an integer")
            retries = int(text)
        elif not isinstance(retries, int):
            raise ConfigError("retries must be an integer")

    tags = raw.get("tags")
    if tags is not None:
        if isinstance(tags, str):
            tags = tags.split(",")
        elif isinstance(tags, (list, tuple)) and all(isinstance(t, str) for t in tags):
            tags = list(tags)
        else:
            raise ConfigError("tags must be a string or a list of strings")

    # -- defaults / normalization -----------------------------------------------------------
    host = "localhost" if host is None else host.strip().lower()
    scheme = "http" if scheme is None else scheme.strip().lower()
    if port is None:
        port = 443 if scheme == "https" else 80
    if timeout is None:
        timeout = 30.0
    if retries is None:
        retries = 3
    normalized: list[str] = []
    for tag in tags or ():
        tag = tag.strip().lower()
        if tag and tag not in normalized:
            normalized.append(tag)

    # -- validation -------------------------------------------------------------------------
    if not host:
        raise ConfigError("host must not be empty")
    if scheme not in ("http", "https"):
        raise ConfigError("scheme must be one of: http, https")
    if not 1 <= port <= 65535:
        raise ConfigError("port must be between 1 and 65535")
    if not 0 < timeout <= 300:
        raise ConfigError("timeout must be greater than 0 and at most 300")
    if not 0 <= retries <= 10:
        raise ConfigError("retries must be between 0 and 10")
    if len(normalized) > 5:
        raise ConfigError("at most 5 tags allowed")
    if scheme == "https" and port == 80:
        raise ConfigError("https cannot use port 80")
    if timeout * (retries + 1) > 600:
        raise ConfigError("timeout * (retries + 1) must not exceed 600")

    return Config(host=host, scheme=scheme, port=port, timeout=timeout, retries=retries,
                  tags=tuple(normalized))
