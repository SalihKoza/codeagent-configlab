import unittest

from stocktrack import inventory, available


class AggregateTests(unittest.TestCase):
    def setUp(self):
        inventory.stock("SKU-PUB-2", "loc-a", 5)
        inventory.stock("SKU-PUB-2", "loc-b", 7)

    def test_available_sums_across_locations(self):
        self.assertEqual(available("SKU-PUB-2"), 12)

    def test_available_single_location(self):
        self.assertEqual(available("SKU-PUB-2", "loc-a"), 5)


if __name__ == "__main__":
    unittest.main()
