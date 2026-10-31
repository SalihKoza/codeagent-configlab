"""Per-SKU/location inventory state and reserve/release bookkeeping."""

_state = {}  # (sku, location) -> {"on_hand": int, "reserved": int}


def _key(sku, location):
    return (sku, location)


def stock(sku, location, on_hand):
    """Test/setup helper: set the on-hand quantity at a location. Not part of the
    candidate-facing task contract - used only to set up scenarios."""
    _state[_key(sku, location)] = {"on_hand": int(on_hand), "reserved": 0}


def known_skus():
    return sorted({sku for (sku, _loc) in _state.keys()})


def locations_for_sku(sku):
    return [loc for (s, loc) in _state.keys() if s == sku]


def reserve(sku, qty, location):
    entry = _state.setdefault(_key(sku, location), {"on_hand": 0, "reserved": 0})
    if qty <= 0:
        return False
    if entry["reserved"] + qty > entry["on_hand"]:
        return False
    entry["reserved"] += qty
    return True


def release(sku, qty, location):
    entry = _state.setdefault(_key(sku, location), {"on_hand": 0, "reserved": 0})
    if qty < 0:
        raise ValueError("qty must not be negative")
    if qty == 0:
        return
    if qty > entry["reserved"]:
        raise ValueError("release exceeds reserved amount")
    entry["reserved"] -= qty
