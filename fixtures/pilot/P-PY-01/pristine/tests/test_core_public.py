import unittest

from rangefmt.core import collapse_ranges, parse_int_list


class CollapseRangesAcceptanceTests(unittest.TestCase):
    """Cases that expose the trailing-run bug reported in statement.md."""

    def test_statement_example_trailing_run(self):
        # statement.md "Bug report": collapse_ranges([4, 7, 8, 9]) == "4,7..9"
        self.assertEqual(collapse_ranges([4, 7, 8, 9]), "4,7..9")

    def test_trailing_run_of_exactly_two(self):
        # statement.md "Contract": "this applies even when the run has exactly two integers"
        self.assertEqual(collapse_ranges([6, 7]), "6..7")


class CollapseRangesRegressionTests(unittest.TestCase):
    """Cases that already work correctly and must keep working."""

    def test_empty_list(self):
        # statement.md "Contract": "An empty input returns \"\"."
        self.assertEqual(collapse_ranges([]), "")

    def test_single_number(self):
        # statement.md "Contract": "A run containing exactly one integer n is rendered as str(n)."
        self.assertEqual(collapse_ranges([5]), "5")

    def test_multiple_groups_trailing_singleton(self):
        # statement.md "Contract": joined with "," + example (variant with trailing singleton)
        self.assertEqual(collapse_ranges([1, 2, 4, 5, 7]), "1..2,4..5,7")

    def test_input_not_mutated(self):
        # statement.md "Contract": "collapse_ranges does not modify the input list."
        values = [1, 2, 3]
        collapse_ranges(values)
        self.assertEqual(values, [1, 2, 3])

    def test_parse_int_list(self):
        self.assertEqual(parse_int_list("3, 1, 2, 1"), [1, 2, 3])
