"""Load a service configuration from raw key/value settings."""

from __future__ import annotations

from typing import Mapping

from .model import Config, ConfigError
from .pipeline import LoaderPipeline

__all__ = ["Config", "ConfigError", "load_config"]

_PIPELINE = LoaderPipeline()


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
    return _PIPELINE.run(raw)
