import unittest

from throttlekit import clock, configure, reset, allow


class FakeClock:
    def __init__(self, t0=1000.0):
        self.t = t0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


class RefillAndConsumeTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeClock()
        clock.set_clock(self.fake)

    def tearDown(self):
        clock.reset_clock()

    def test_refill_over_time_allows_expected_count(self):
        configure("public-client-a", rate_per_sec=1.0, burst=10.0)
        reset("public-client-a")
        self.fake.advance(3.7)
        allowed = sum(1 for _ in range(4) if allow("public-client-a"))
        self.assertEqual(allowed, 3)

    def test_deny_when_well_below_a_token(self):
        configure("public-client-b", rate_per_sec=1.0, burst=10.0)
        reset("public-client-b")
        self.fake.advance(0.2)
        self.assertFalse(allow("public-client-b"))

    def test_burst_cap_limits_refill(self):
        configure("public-client-c", rate_per_sec=10.0, burst=2.0)
        reset("public-client-c")
        self.fake.advance(100.0)
        self.assertTrue(allow("public-client-c"))
        self.assertTrue(allow("public-client-c"))
        self.assertFalse(allow("public-client-c"))


if __name__ == "__main__":
    unittest.main()
