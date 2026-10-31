"""Hidden acceptance tests for S2-PY-BUG-01: allow() boundary consistency."""

import unittest

from throttlekit import clock, configure, reset, allow


class FakeClock:
    def __init__(self, t0=5000.0):
        self.t = t0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


class BoundaryAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeClock()
        clock.set_clock(self.fake)

    def tearDown(self):
        clock.reset_clock()

    def test_allow_at_exactly_one_token(self):
        configure("hidden-client-1", rate_per_sec=1.0, burst=5.0)
        reset("hidden-client-1")
        self.fake.advance(1.0)  # tokens == 1.0 exactly
        self.assertTrue(allow("hidden-client-1"))

    def test_allow_at_boundary_reached_via_post_consumption_remainder(self):
        # Reach the exact 1.0-token boundary via a different code path than a fresh
        # refill: accumulate 2.0 tokens, consume one, then check the exact 1.0 remainder.
        configure("hidden-client-2", rate_per_sec=1.0, burst=5.0)
        reset("hidden-client-2")
        self.fake.advance(2.0)  # tokens == 2.0 exactly
        self.assertTrue(allow("hidden-client-2"))  # consumes to exactly 1.0 remaining
        self.assertTrue(allow("hidden-client-2"))  # must also allow at the 1.0 remainder

    def test_deny_strictly_below_one_token(self):
        configure("hidden-client-3", rate_per_sec=1.0, burst=5.0)
        reset("hidden-client-3")
        self.fake.advance(0.999)
        self.assertFalse(allow("hidden-client-3"))

    def test_allow_strictly_above_one_token_and_consumes(self):
        configure("hidden-client-4", rate_per_sec=1.0, burst=5.0)
        reset("hidden-client-4")
        self.fake.advance(1.5)
        self.assertTrue(allow("hidden-client-4"))
        # tokens should now be 0.5 - no further elapsed time - must deny
        self.assertFalse(allow("hidden-client-4"))


if __name__ == "__main__":
    unittest.main()
