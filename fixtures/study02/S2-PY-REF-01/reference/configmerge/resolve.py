"""Dotted-path traversal + merge logic for configmerge."""

from . import layers as _layers_mod


def resolve(key):
    stack = _layers_mod.layers()
    for layer in reversed(stack):  # most-specific first
        value, found = _layers_mod.get_dotted(layer.data, key)
        if found:
            return value
    return None
