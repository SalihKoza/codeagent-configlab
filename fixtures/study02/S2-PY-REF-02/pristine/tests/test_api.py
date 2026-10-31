import unittest

from throttlekit import clock, configure, reset, allow


class FakeClock:
    def __init__(self, t0=2000.0):
        self.t = t0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


class PublicApiTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeClock()
        clock.set_clock(self.fake)

    def tearDown(self):
        clock.reset_clock()

    def test_reset_starts_with_no_tokens(self):
        configure("public-client-d", rate_per_sec=1.0, burst=5.0)
        reset("public-client-d")
        self.assertFalse(allow("public-client-d"))

    def test_configure_then_wait_then_allow(self):
        configure("public-client-e", rate_per_sec=1.0, burst=5.0)
        reset("public-client-e")
        self.fake.advance(2.5)
        self.assertTrue(allow("public-client-e"))

    def test_multi_client_isolation(self):
        configure("public-client-f", rate_per_sec=1.0, burst=5.0)
        configure("public-client-g", rate_per_sec=1.0, burst=5.0)
        reset("public-client-f")
        reset("public-client-g")
        self.fake.advance(3.5)
        self.assertTrue(allow("public-client-f"))
        self.assertTrue(allow("public-client-f"))
        self.assertTrue(allow("public-client-f"))
        self.assertFalse(allow("public-client-f"))
        # client-g's bucket must be unaffected by client-f's consumption
        self.assertTrue(allow("public-client-g"))


if __name__ == "__main__":
    unittest.main()
