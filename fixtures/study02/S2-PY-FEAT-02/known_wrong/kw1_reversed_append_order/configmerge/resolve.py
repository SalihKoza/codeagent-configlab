"""Dotted-path traversal + merge logic for configmerge.

KNOWN-WRONG VARIANT (kw1_reversed_append_order): concatenates list layers in most-specific-first
order instead of least-to-most-specific, violating the frozen append-order contract.
"""

from . import layers as _layers_mod


def resolve(key, list_strategy="replace"):
    stack = _layers_mod.layers()

    if list_strategy == "append":
        has_list_value = any(
            isinstance(_layers_mod.get_dotted(layer["data"], key)[0], list)
            and _layers_mod.get_dotted(layer["data"], key)[1]
            for layer in stack
        )
        if has_list_value:
            result = []
            # BUG: iterates most-specific-first instead of least-to-most-specific.
            for layer in reversed(stack):
                value, found = _layers_mod.get_dotted(layer["data"], key)
                if found and isinstance(value, list):
                    result.extend(value)
            return result

    for layer in reversed(stack):
        value, found = _layers_mod.get_dotted(layer["data"], key)
        if found:
            return value
    return None
