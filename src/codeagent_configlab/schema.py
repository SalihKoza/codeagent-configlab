"""A tiny, dependency-free JSON-Schema subset validator.

We ship real JSON-Schema files under ``schemas/`` as the documented contract, and validate
against them here without requiring the ``jsonschema`` package (the harness must run with no
pip install). Only the keywords the manifest/result schemas actually use are supported:

* ``type`` (string name or list of names: object, array, string, integer, number, boolean, null)
* ``required``
* ``properties``
* ``additionalProperties`` (bool)
* ``enum``
* ``const``
* ``items`` (single subschema for arrays)
* ``oneOf`` (validates against exactly one branch — used for the OPEN-sentinel-or-value fields)

It returns a list of human-readable error paths (empty == valid). It is intentionally strict
and small; it is not a general JSON-Schema implementation.
"""

from __future__ import annotations

from typing import Any

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    # bool is a subclass of int in Python; exclude it from integer/number.
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def _check_type(value: Any, type_spec: Any) -> bool:
    names = type_spec if isinstance(type_spec, list) else [type_spec]
    return any(_TYPE_CHECKS[n](value) for n in names if n in _TYPE_CHECKS)


def _validate(value: Any, schema: dict, path: str, errors: list[str]) -> None:
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {value!r}")
        return

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in enum {schema['enum']!r}")

    if "oneOf" in schema:
        matches = 0
        for branch in schema["oneOf"]:
            branch_errors: list[str] = []
            _validate(value, branch, path, branch_errors)
            if not branch_errors:
                matches += 1
        if matches != 1:
            errors.append(f"{path}: matched {matches} of oneOf branches (expected exactly 1)")
        return

    if "type" in schema and not _check_type(value, schema["type"]):
        errors.append(f"{path}: expected type {schema['type']!r}, got {type(value).__name__}")
        return  # further keyword checks assume the type held

    if isinstance(value, dict) and schema.get("type") == "object":
        props: dict = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in value:
                errors.append(f"{path}: missing required property {req!r}")
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(props)
            if extra:
                errors.append(f"{path}: unexpected properties {sorted(extra)!r}")
        for key, subschema in props.items():
            if key in value:
                _validate(value[key], subschema, f"{path}.{key}", errors)

    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            _validate(item, schema["items"], f"{path}[{i}]", errors)


def validate(instance: Any, schema: dict) -> list[str]:
    """Validate *instance* against *schema*; return a list of error strings (empty == valid)."""
    errors: list[str] = []
    _validate(instance, schema, "$", errors)
    return errors


class SchemaError(ValueError):
    """Raised by :func:`validate_or_raise` when an instance does not conform."""


def validate_or_raise(instance: Any, schema: dict) -> None:
    errors = validate(instance, schema)
    if errors:
        raise SchemaError("; ".join(errors))
