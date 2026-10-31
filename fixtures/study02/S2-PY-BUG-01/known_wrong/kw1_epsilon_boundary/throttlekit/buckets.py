"""Per-client bucket state and refill/consume logic for throttlekit.

KNOWN-WRONG VARIANT (kw1_epsilon_boundary): fixes the boundary comparison correctly to `>=`,
but the same edit accidentally drops the burst cap (the `min(burst, ...)` clamp) while touching
that line, so refill becomes unbounded. Authoring note: the literal "epsilon hack that fails at a
second integer boundary" originally sketched for this class is not distinguishable in this
concrete implementation, because the comparison is always against the fixed constant 1.0 (there
is only one discrete boundary value, not several); this variant substitutes an equally plausible,
genuinely-catchable mistake (caught by the existing burst-cap regression test) instead, and that
substitution is documented in the Gate-5 implementation report.
"""

from . import clock

_buckets = {}


def _get_or_create(client_id):
    if client_id not in _buckets:
        _buckets[client_id] = {
            "tokens": 0.0,
            "last_refill": clock.now(),
            "rate": 0.0,
            "burst": 0.0,
        }
    return _buckets[client_id]


def configure(client_id, rate_per_sec, burst):
    bucket = _get_or_create(client_id)
    bucket["rate"] = float(rate_per_sec)
    bucket["burst"] = float(burst)


def reset(client_id):
    bucket = _get_or_create(client_id)
    bucket["tokens"] = 0.0
    bucket["last_refill"] = clock.now()


def allow(client_id):
    bucket = _get_or_create(client_id)
    now = clock.now()
    elapsed = now - bucket["last_refill"]
    # BUG: burst cap accidentally dropped while fixing the boundary comparison below.
    bucket["tokens"] = bucket["tokens"] + elapsed * bucket["rate"]
    bucket["last_refill"] = now
    if bucket["tokens"] >= 1.0:
        bucket["tokens"] -= 1.0
        return True
    return False
