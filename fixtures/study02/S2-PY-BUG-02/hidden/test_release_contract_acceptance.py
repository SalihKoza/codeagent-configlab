"""Hidden acceptance tests for S2-PY-BUG-02: release() over-release contract."""

import unittest

from stocktrack import inventory, reserve, release, available


class ReleaseContractTests(unittest.TestCase):
    def setUp(self):
        inventory.stock("SKU-HID-1", "loc-h", 20)

    def test_negative_qty_raises_and_state_unchanged(self):
        reserve("SKU-HID-1", 5, "loc-h")
        with self.assertRaises(ValueError):
            release("SKU-HID-1", -3, "loc-h")
        self.assertEqual(available("SKU-HID-1", "loc-h"), 15)

    def test_zero_qty_is_noop(self):
        reserve("SKU-HID-1", 5, "loc-h")
        release("SKU-HID-1", 0, "loc-h")
        self.assertEqual(available("SKU-HID-1", "loc-h"), 15)

    def test_in_bound_release_decrements(self):
        reserve("SKU-HID-1", 5, "loc-h")
        release("SKU-HID-1", 3, "loc-h")
        self.assertEqual(available("SKU-HID-1", "loc-h"), 18)

    def test_over_release_raises_and_state_fully_unchanged(self):
        reserve("SKU-HID-1", 5, "loc-h")
        with self.assertRaises(ValueError):
            release("SKU-HID-1", 10, "loc-h")
        # Must remain exactly 15 (on_hand=20, reserved=5) - never 20 (as a silent
        # clamp-to-zero fix would produce) and never negative.
        self.assertEqual(available("SKU-HID-1", "loc-h"), 15)


if __name__ == "__main__":
    unittest.main()
