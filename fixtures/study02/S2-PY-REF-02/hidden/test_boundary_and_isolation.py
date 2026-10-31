"""Hidden acceptance tests for S2-PY-REF-02: Bucket representation refactor.

Re-runs the boundary cases from S2-PY-BUG-01 (must remain byte-identical after the refactor)
plus a multi-client isolation check that would catch a shared-default-object bug.
"""

import unittest

from throttlekit import clock, configure, reset, allow


class FakeClock:
    def __init__(self, t0=9000.0):
        self.t = t0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


class BoundaryRegressionTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeClock()
        clock.set_clock(self.fake)

    def tearDown(self):
        clock.reset_clock()

    def test_allow_at_exactly_one_token(self):
        configure("hidden-ref-client-1", rate_per_sec=1.0, burst=5.0)
        reset("hidden-ref-client-1")
        self.fake.advance(1.0)
        self.assertTrue(allow("hidden-ref-client-1"))

    def test_deny_strictly_below_one_token(self):
        configure("hidden-ref-client-2", rate_per_sec=1.0, burst=5.0)
        reset("hidden-ref-client-2")
        self.fake.advance(0.999)
        self.assertFalse(allow("hidden-ref-client-2"))


class MultiClientIsolationTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeClock(t0=9500.0)
        clock.set_clock(self.fake)

    def tearDown(self):
        clock.reset_clock()

    def test_two_newly_touched_clients_do_not_share_state(self):
        # Touch two brand-new client ids without configuring them identically, and
        # confirm one client's configuration/consumption never leaks to the other.
        configure("isolated-client-x", rate_per_sec=1.0, burst=5.0)
        configure("isolated-client-y", rate_per_sec=1.0, burst=5.0)
        reset("isolated-client-x")
        reset("isolated-client-y")
        self.fake.advance(3.0)
        # Drain client-x completely.
        self.assertTrue(allow("isolated-client-x"))
        self.assertTrue(allow("isolated-client-x"))
        self.assertTrue(allow("isolated-client-x"))
        self.assertFalse(allow("isolated-client-x"))
        # client-y must still have its own full 3.0 tokens available - unaffected by x.
        self.assertTrue(allow("isolated-client-y"))
        self.assertTrue(allow("isolated-client-y"))
        self.assertTrue(allow("isolated-client-y"))
        self.assertFalse(allow("isolated-client-y"))


if __name__ == "__main__":
    unittest.main()
