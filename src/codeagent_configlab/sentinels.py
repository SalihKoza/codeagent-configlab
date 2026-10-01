"""Explicit ``OPEN`` vs not-applicable (``None``) semantics.

The protocol (§12) carries decisions that are deliberately **OPEN** — not yet frozen
(e.g. the model pin O5, the wall-clock cap O12). Those must never be silently filled with
a plausible-looking default, because a default could accidentally become the frozen value.

We therefore distinguish two absences:

* ``OPEN`` — a decision that is undecided and *must* be frozen before final runs. It
  serializes to the JSON string ``"OPEN"`` so it is visibly not a real value.
* ``None`` (``NA``) — a field that does not apply to this configuration (e.g. the C2
  planning tool set on a C0 run). It serializes to JSON ``null``.

Keeping these distinct lets the schema and validator enforce, per configuration, which
fields must be ``null`` (not applicable) versus which may still be ``"OPEN"`` (undecided).
"""

from __future__ import annotations

# Sentinel string for an undecided, not-yet-frozen decision. Chosen as a plain string so
# it round-trips through JSON unchanged and is obvious in any artifact.
OPEN = "OPEN"

# Not-applicable is represented by Python ``None`` / JSON ``null``. ``NA`` is an alias used
# for readability at call sites.
NA = None


def is_open(value: object) -> bool:
    """True iff *value* is the OPEN sentinel (an undecided, unfrozen decision)."""
    return value == OPEN


def is_na(value: object) -> bool:
    """True iff *value* is not-applicable (``None``)."""
    return value is None
