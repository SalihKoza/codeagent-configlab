"""Hidden acceptance tests for S2-PY-FEAT-01: low_stock_skus()."""

import unittest

from stocktrack import inventory
from stocktrack.aggregate import low_stock_skus


class LowStockTests(unittest.TestCase):
    def setUp(self):
        inventory.stock("SKU-A", "loc-1", 3)
        inventory.stock("SKU-A", "loc-2", 4)  # SKU-A total = 7, multi-location
        inventory.stock("SKU-B", "loc-1", 2)  # SKU-B total = 2
        inventory.stock("SKU-C", "loc-1", 100)  # SKU-C total = 100

    def test_multi_location_sku_aggregated_before_threshold(self):
        # SKU-A's true total (7) must be used, not just one location's quantity (3).
        result = low_stock_skus(5)
        self.assertNotIn("SKU-A", result)
        self.assertIn("SKU-B", result)

    def test_threshold_zero_returns_only_zero_or_below(self):
        inventory.stock("SKU-D", "loc-1", 0)
        result = low_stock_skus(0)
        self.assertIn("SKU-D", result)
        self.assertNotIn("SKU-A", result)
        self.assertNotIn("SKU-B", result)
        self.assertNotIn("SKU-C", result)

    def test_threshold_above_all_returns_full_catalog_sorted_ascending(self):
        result = low_stock_skus(1000)
        self.assertEqual(set(result), {"SKU-A", "SKU-B", "SKU-C"})
        self.assertLess(result.index("SKU-B"), result.index("SKU-A"))
        self.assertLess(result.index("SKU-A"), result.index("SKU-C"))

    def test_tie_break_by_sku_name_ascending(self):
        inventory.stock("SKU-TIE-2", "loc-1", 5)
        inventory.stock("SKU-TIE-1", "loc-1", 5)
        result = low_stock_skus(5)
        self.assertLess(result.index("SKU-TIE-1"), result.index("SKU-TIE-2"))


if __name__ == "__main__":
    unittest.main()
