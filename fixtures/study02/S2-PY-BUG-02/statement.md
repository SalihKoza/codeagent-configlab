# `stocktrack`: `release()` must reject an over-release

## Objective

`release(sku, qty, location)` must never allow a location's reserved quantity to go negative.

## Current behavior

`release()` currently subtracts `qty` from the location's reserved quantity without checking
whether that much is actually reserved, which can drive the reserved count below zero.

## Required behavior

`release(sku, qty, location)` must behave exactly as follows:
- `qty < 0`: raise `ValueError`; inventory state must be unchanged.
- `qty == 0`: no-op; return normally; state unchanged.
- `0 < qty <= (current reserved quantity at that location)`: decrement reserved by `qty` (today's
  normal-path behavior).
- `qty > (current reserved quantity at that location)`: raise `ValueError`; inventory state must
  be **entirely unchanged** — no partial mutation.

## Preservation requirements

`reserve()` and `available()` must be unaffected. Normal, in-bound `release()` calls must behave
exactly as they do today.

## Scope / integrity rules

Only this repository's global write-scope policy applies.

## Validation guidance

Run `python3 -m unittest discover -s tests -v` from the repository root. The existing
`tests/test_inventory.py` exercises reserve/release behavior directly.

## Non-requirements

You do not need to introduce a custom exception type; `ValueError` is sufficient. You do not need
to change `reserve()`'s or `available()`'s signatures.
