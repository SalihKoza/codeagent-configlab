"""configmerge — layered configuration resolution (base + environment + per-instance overrides)."""

from .resolve import resolve
from .layers import set_override, layers

__all__ = ["resolve", "set_override", "layers"]
