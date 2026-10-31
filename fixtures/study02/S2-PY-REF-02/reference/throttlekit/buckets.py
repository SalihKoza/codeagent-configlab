"""Per-client bucket state and refill/consume logic for throttlekit (Bucket structure)."""

from dataclasses import dataclass

from . import clock


@dataclass
class Bucket:
    tokens: float = 0.0
    last_refill: float = 0.0
    rate: float = 0.0
    burst: float = 0.0


_buckets: dict = {}


def _get_or_create(client_id):
    if client_id not in _buckets:
        _buckets[client_id] = Bucket(tokens=0.0, last_refill=clock.now(), rate=0.0, burst=0.0)
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
