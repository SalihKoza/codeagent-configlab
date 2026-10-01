import unittest

from rangefmt.core import collapse_ranges


class CollapseRangesHiddenTests(unittest.TestCase):
    def test_length_two_trailing_group_after_singleton(self):
        # statement.md: trailing-run rule + "," joining of multiple runs
        self.assertEqual(collapse_ranges([1, 3, 4]), "1,3..4")

    def test_negative_trailing_group(self):
        # statement.md: ".." stays unambiguous for negative start/end
        self.assertEqual(collapse_ranges([-5, -4, -3]), "-5..-3")

    def test_long_trailing_run(self):
        # statement.md: general trailing-run rule, length > 3
        self.assertEqual(collapse_ranges([10, 20, 21, 22, 23, 24]), "10,20..24")

    def test_single_element_negative(self):
        # statement.md: single-run rendering, "may contain negative integers"
        self.assertEqual(collapse_ranges([-7]), "-7")

    def test_whole_input_is_one_run(self):
        # statement.md: general contract, no leading singleton before the (only) run
        self.assertEqual(collapse_ranges([2, 3, 4, 5]), "2..5")
