"""Injectable time source for throttlekit.

All time-dependent code in this package must read the current time through this module's
``now()`` function, never through a direct wall-clock call, so that tests can control elapsed
time deterministically.
"""

import time

_clock = time.monotonic


def now() -> float:
    return _clock()


def set_clock(fn) -> None:
    """Test-only hook: replace the time source with ``fn() -> float`` (seconds)."""
    global _clock
    _clock = fn


def reset_clock() -> None:
    """Test-only hook: restore the real wall-clock time source."""
    global _clock
    _clock = time.monotonic
