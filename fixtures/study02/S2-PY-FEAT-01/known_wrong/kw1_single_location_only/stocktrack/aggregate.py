"""Cross-location query helpers for stocktrack.

KNOWN-WRONG VARIANT (kw1_single_location_only): low_stock_skus reads only one (arbitrary)
location's quantity per SKU instead of aggregating across all of that SKU's locations.
"""

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
    totals = {}
    for sku in inventory.known_skus():
        # BUG: only reads the first location found for this SKU instead of summing all.
        locs = inventory.locations_for_sku(sku)
        entry = inventory._state[inventory._key(sku, locs[0])]
        totals[sku] = entry["on_hand"] - entry["reserved"]
    filtered = [sku for sku, qty in totals.items() if qty <= threshold]
    filtered.sort(key=lambda sku: (totals[sku], sku))
    return filtered
