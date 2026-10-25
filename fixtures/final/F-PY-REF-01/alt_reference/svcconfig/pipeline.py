"""The staged loading pipeline behind ``load_config``."""

from __future__ import annotations

from typing import Any, Mapping

from .model import Config, ConfigError


class LoaderPipeline:
    """Runs the three loading stages in order and builds the resulting :class:`Config`."""

    FIELDS = ("host", "scheme", "port", "timeout", "retries", "tags")
    DEFAULTS = {"host": "localhost", "scheme": "http", "timeout": 30.0, "retries": 3}
    CHECKS = (
        ("host must not be empty", lambda c: bool(c["host"])),
        ("scheme must be one of: http, https", lambda c: c["scheme"] in ("http", "https")),
        ("port must be between 1 and 65535", lambda c: 1 <= c["port"] <= 65535),
        ("timeout must be greater than 0 and at most 300", lambda c: 0 < c["timeout"] <= 300),
        ("retries must be between 0 and 10", lambda c: 0 <= c["retries"] <= 10),
        ("at most 5 tags allowed", lambda c: len(c["tags"]) <= 5),
        ("https cannot use port 80", lambda c: not (c["scheme"] == "https" and c["port"] == 80)),
        ("timeout * (retries + 1) must not exceed 600",
         lambda c: c["timeout"] * (c["retries"] + 1) <= 600),
    )

    def run(self, raw: Mapping[str, object]) -> Config:
        data: Any = raw
        for stage in (self.parse_values, self.apply_defaults, self.validate_values):
            data = stage(data)
        return Config(**data)

    # -- stage 1 ----------------------------------------------------------------------------
    def parse_values(self, raw: Mapping[str, object]) -> dict:
        for key in sorted(raw):
            if key not in self.FIELDS:
                raise ConfigError(f"unknown setting: {key}")
        parsed = {}
        for name in self.FIELDS:
            value = raw.get(name)
            if value is not None:
                value = self._coerce(name, value)
            parsed[name] = value
        return parsed

    def _coerce(self, name: str, value: object) -> object:
        if name in ("host", "scheme"):
            if isinstance(value, str):
                return value
            raise ConfigError(f"{name} must be a string")
        if name in ("port", "retries"):
            if isinstance(value, int) and not isinstance(value, bool):
                return value
            if isinstance(value, str) and value.strip().isascii() and value.strip().isdigit():
                return int(value.strip())
            raise ConfigError(f"{name} must be an integer")
        if name == "timeout":
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value.strip())
                except ValueError:
                    pass
            raise ConfigError("timeout must be a number")
        if isinstance(value, str):
            return value.split(",")
        if isinstance(value, (list, tuple)) and all(isinstance(t, str) for t in value):
            return list(value)
        raise ConfigError("tags must be a string or a list of strings")

    # -- stage 2 ----------------------------------------------------------------------------
    def apply_defaults(self, parsed: dict) -> dict:
        out = dict(parsed)
        for key in ("host", "scheme"):
            if out[key] is not None:
                out[key] = out[key].strip().lower()
        for key, default in self.DEFAULTS.items():
            out.setdefault(key, None)
            if out[key] is None:
                out[key] = default
        if out["port"] is None:
            out["port"] = 443 if out["scheme"] == "https" else 80
        out["tags"] = tuple(dict.fromkeys(
            t for t in (s.strip().lower() for s in out["tags"] or ()) if t))
        return out

    # -- stage 3 ----------------------------------------------------------------------------
    def validate_values(self, cfg: dict) -> dict:
        for message, holds in self.CHECKS:
            if not holds(cfg):
                raise ConfigError(message)
        return cfg
