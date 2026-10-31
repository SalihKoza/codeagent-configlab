import unittest

from stocktrack import inventory, reserve, release, available


class ReserveReleaseTests(unittest.TestCase):
    def setUp(self):
        inventory.stock("SKU-PUB-1", "loc-a", 10)

    def test_reserve_and_available(self):
        self.assertTrue(reserve("SKU-PUB-1", 4, "loc-a"))
        self.assertEqual(available("SKU-PUB-1", "loc-a"), 6)

    def test_release_within_bound(self):
        reserve("SKU-PUB-1", 5, "loc-a")
        release("SKU-PUB-1", 5, "loc-a")
        self.assertEqual(available("SKU-PUB-1", "loc-a"), 10)

    def test_reserve_cannot_exceed_on_hand(self):
        self.assertFalse(reserve("SKU-PUB-1", 11, "loc-a"))


if __name__ == "__main__":
    unittest.main()
