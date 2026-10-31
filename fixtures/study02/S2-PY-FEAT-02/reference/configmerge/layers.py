"""Layer stack representation for configmerge.

Layers are kept least-specific-first, most-specific-last (base, then environment, then
per-instance override, applied in that order).
"""

_layers = []  # list of {"name": str, "precedence": int, "data": dict}

_OVERRIDE_LAYER_NAME = "__override__"
_OVERRIDE_PRECEDENCE = 1_000_000


def add_layer(name, data, precedence=None):
    """Test/setup helper: add a layer to the stack. Not part of the candidate-facing
    task contract - used only to set up scenarios."""
    if precedence is None:
        precedence = len(_layers)
    _layers.append({"name": name, "precedence": precedence, "data": data})
    _layers.sort(key=lambda layer: layer["precedence"])


def clear_layers():
    """Test/setup helper: reset the layer stack between test cases."""
    _layers.clear()


def layers():
    return list(_layers)


def _ensure_override_layer():
    for layer in _layers:
        if layer["name"] == _OVERRIDE_LAYER_NAME:
            return layer
    layer = {"name": _OVERRIDE_LAYER_NAME, "precedence": _OVERRIDE_PRECEDENCE, "data": {}}
    _layers.append(layer)
    _layers.sort(key=lambda l: l["precedence"])
    return layer


def set_override(key, value):
    layer = _ensure_override_layer()
    set_dotted(layer["data"], key, value)


def get_dotted(data, key):
    parts = key.split(".")
    node = data
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return None, False
        node = node[part]
    return node, True


def set_dotted(data, key, value):
    parts = key.split(".")
    node = data
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value
