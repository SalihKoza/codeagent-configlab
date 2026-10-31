"""Dotted-path traversal + merge logic for configmerge."""

from . import layers as _layers_mod


def resolve(key, list_strategy="replace"):
    stack = _layers_mod.layers()  # least-specific first, most-specific last

    if list_strategy == "append":
        has_list_value = any(
            isinstance(_layers_mod.get_dotted(layer["data"], key)[0], list)
            and _layers_mod.get_dotted(layer["data"], key)[1]
            for layer in stack
        )
        if has_list_value:
            result = []
            for layer in stack:  # least-specific first, most-specific last
                value, found = _layers_mod.get_dotted(layer["data"], key)
                if found and isinstance(value, list):
                    result.extend(value)
            return result
        # not a list-valued key anywhere -> falls through to replace semantics below

    for layer in reversed(stack):  # most-specific first
        value, found = _layers_mod.get_dotted(layer["data"], key)
        if found:
            return value
    return None
