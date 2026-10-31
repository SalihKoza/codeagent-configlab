# `stocktrack`: add `low_stock_skus(threshold)`

## Objective

Add a new function that reports which SKUs are running low across the entire warehouse.

## Current behavior

`available(sku)` already reports total available quantity for one SKU, summed across all
locations that carry it. There is currently no way to query across the whole SKU catalog at once.

## Required behavior

Add `low_stock_skus(threshold: int) -> list[str]`, returning every SKU whose total available
quantity (summed across all of that SKU's locations, exactly as `available(sku)` already
computes it) is less than or equal to `threshold`, ordered by ascending available quantity (ties
broken by SKU name, ascending). A `threshold` of 0 returns only SKUs with zero or below-available
quantity; a `threshold` at or above every SKU's total returns the full catalog.

## Preservation requirements

`reserve()`, `release()`, and the existing single-SKU `available()` query must be unaffected.

## Scope / integrity rules

Only this repository's global write-scope policy applies.

## Validation guidance

Run `python3 -m unittest discover -s tests -v` from the repository root. `tests/test_aggregate.py`
covers the aggregation layer this function extends.

## Non-requirements

You do not need to support filtering by location in this function; it reports warehouse-wide
totals only.
