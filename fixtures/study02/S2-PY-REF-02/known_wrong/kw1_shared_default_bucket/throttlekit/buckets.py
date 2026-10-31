"""Per-client bucket state and refill/consume logic for throttlekit (Bucket structure).

KNOWN-WRONG VARIANT (kw1_shared_default_bucket): a single shared "default" Bucket instance is
reused across every newly-touched client instead of allocating an independent one, so any
client's first configure()/allow() call mutates state visible to any other client that also
hasn't been independently allocated yet - a classic shared-mutable-default leak.
"""

from dataclasses import dataclass

from . import clock


@dataclass
class Bucket:
    tokens: float = 0.0
    last_refill: float = 0.0
    rate: float = 0.0
    burst: float = 0.0


_DEFAULT_BUCKET = Bucket()  # BUG: one shared instance, not a fresh template per client.
_buckets: dict = {}


def _get_or_create(client_id):
    if client_id not in _buckets:
        # BUG: every brand-new client shares the exact same Bucket object.
        _buckets[client_id] = _DEFAULT_BUCKET
    return _buckets[client_id]


def configure(client_id, rate_per_sec, burst):
    bucket = _get_or_create(client_id)
    bucket.rate = float(rate_per_sec)
    bucket.burst = float(burst)


def reset(client_id):
    bucket = _get_or_create(client_id)
    bucket.tokens = 0.0
    bucket.last_refill = clock.now()


def allow(client_id):
    bucket = _get_or_create(client_id)
    now = clock.now()
    elapsed = now - bucket.last_refill
    bucket.tokens = min(bucket.burst, bucket.tokens + elapsed * bucket.rate)
    bucket.last_refill = now
    if bucket.tokens >= 1.0:
        bucket.tokens -= 1.0
        return True
    return False
