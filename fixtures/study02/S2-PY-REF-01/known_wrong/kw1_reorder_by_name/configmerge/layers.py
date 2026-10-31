"""Layer stack representation for configmerge (explicit Layer structure).

KNOWN-WRONG VARIANT (kw1_reorder_by_name): sorts layers by name instead of preserving the
original precedence order - passes if layer names happen to sort alphabetically into
precedence order, fails otherwise.
"""

from dataclasses import dataclass, field


@dataclass
class Layer:
    name: str
    precedence: int
    data: dict = field(default_factory=dict)

    def __getitem__(self, key):
        return getattr(self, key)

    def __contains__(self, key):
        return hasattr(self, key)


_layers: list = []

_OVERRIDE_LAYER_NAME = "__override__"
_OVERRIDE_PRECEDENCE = 1_000_000


def add_layer(name, data, precedence=None):
    if precedence is None:
        precedence = len(_layers)
    _layers.append(Layer(name=name, precedence=precedence, data=data))
    # BUG: reorders by name instead of preserving precedence.
    _layers.sort(key=lambda layer: layer.name)


def clear_layers():
    _layers.clear()


def layers():
    return list(_layers)


def _ensure_override_layer():
    for layer in _layers:
        if layer.name == _OVERRIDE_LAYER_NAME:
            return layer
    layer = Layer(name=_OVERRIDE_LAYER_NAME, precedence=_OVERRIDE_PRECEDENCE, data={})
    _layers.append(layer)
    _layers.sort(key=lambda l: l.name)
    return layer


def set_override(key, value):
    layer = _ensure_override_layer()
    set_dotted(layer.data, key, value)


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
