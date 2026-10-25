"""Parse / default / validate stages used by ``load_config``."""

from __future__ import annotations

from typing import Mapping

from .model import ConfigError

FIELDS = ("host", "scheme", "port", "timeout", "retries", "tags")


def _text(name):
    def parse(value):
        if not isinstance(value, str):
            raise ConfigError(f"{name} must be a string")
        return value
    return parse


def _whole(name):
    def parse(value):
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ConfigError(f"{name} must be an integer")
        if isinstance(value, str):
            text = value.strip()
            if not (text.isascii() and text.isdigit()):
                raise ConfigError(f"{name} must be an integer")
            return int(text)
        return value
    return parse


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ConfigError("timeout must be a number")
    try:
        return float(value.strip() if isinstance(value, str) else value)
    except ValueError:
        raise ConfigError("timeout must be a number") from None


def _tag_list(value):
    if isinstance(value, str):
        return value.split(",")
    if not isinstance(value, (list, tuple)) or not all(isinstance(t, str) for t in value):
        raise ConfigError("tags must be a string or a list of strings")
    return list(value)


PARSERS = {"host": _text("host"), "scheme": _text("scheme"), "port": _whole("port"),
           "timeout": _number, "retries": _whole("retries"), "tags": _tag_list}


def parse_values(raw: Mapping[str, object]) -> dict:
    unknown = [k for k in raw if k not in PARSERS]
    if unknown:
        raise ConfigError(f"unknown setting: {min(unknown)}")
    return {name: (None if raw.get(name) is None else PARSERS[name](raw.get(name)))
            for name in FIELDS}


def _normalized(text):
    return text.strip().lower()


def apply_defaults(parsed: dict) -> dict:
    scheme = "http" if parsed["scheme"] is None else _normalized(parsed["scheme"])
    seen = []
    for tag in map(_normalized, parsed["tags"] or ()):
        if tag and tag not in seen:
            seen.append(tag)
    return {
        "host": _normalized(parsed["host"]) if parsed["host"] is not None else "localhost",
        "scheme": scheme,
        "port": parsed["port"] if parsed["port"] is not None else (443 if scheme == "https" else 80),
        "timeout": parsed["timeout"] if parsed["timeout"] is not None else 30.0,
        "retries": parsed["retries"] if parsed["retries"] is not None else 3,
        "tags": tuple(seen),
    }


def _single(cfg):
    yield not cfg["host"], "host must not be empty"
    yield cfg["scheme"] not in ("http", "https"), "scheme must be one of: http, https"
    yield not 1 <= cfg["port"] <= 65535, "port must be between 1 and 65535"
    yield not 0 < cfg["timeout"] <= 300, "timeout must be greater than 0 and at most 300"
    yield not 0 <= cfg["retries"] <= 10, "retries must be between 0 and 10"
    yield len(cfg["tags"]) > 5, "at most 5 tags allowed"


def _cross(cfg):
    yield cfg["scheme"] == "https" and cfg["port"] == 80, "https cannot use port 80"
    yield (cfg["timeout"] * (cfg["retries"] + 1) > 600,
           "timeout * (retries + 1) must not exceed 600")


def validate_values(cfg: dict) -> dict:
    for check in (_single, _cross):
        for failed, message in check(cfg):
            if failed:
                raise ConfigError(message)
    return cfg
