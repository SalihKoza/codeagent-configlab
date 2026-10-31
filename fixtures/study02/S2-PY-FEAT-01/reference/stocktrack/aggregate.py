"""Cross-location query helpers for stocktrack, built on top of inventory.py's state."""

from . import inventory


def available(sku, location=None):
    if location is not None:
        entry = inventory._state.get(inventory._key(sku, location))
        if entry is None:
            return 0
        return entry["on_hand"] - entry["reserved"]
    total = 0
    for loc in inventory.locations_for_sku(sku):
        entry = inventory._state[inventory._key(sku, loc)]
        total += entry["on_hand"] - entry["reserved"]
    return total


def low_stock_skus(threshold):
    totals = {sku: available(sku) for sku in inventory.known_skus()}
    filtered = [sku for sku, qty in totals.items() if qty <= threshold]
    filtered.sort(key=lambda sku: (totals[sku], sku))
    return filtered
