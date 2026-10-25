import inspect
import unittest

from msgheaders import Headers


class HeadersRegressionTests(unittest.TestCase):
    """Behavior that must stay as it is (statement items 8-10 and the class docstring)."""

    def test_add_appends_case_variants_as_separate_entries(self):
        # item 8
        h = Headers()
        self.assertIsNone(h.add("Via", "1"))
        h.add("VIA", "2")
        h.add("via", "3")
        self.assertEqual(h.items(), [("Via", "1"), ("VIA", "2"), ("via", "3")])
        self.assertEqual(len(h), 3)

    def test_add_keeps_exact_duplicates(self):
        # item 8
        h = Headers([("Warning", "a")])
        h.add("Warning", "a")
        self.assertEqual(h.get_all("warning"), ["a", "a"])

    def test_constructor_keeps_all_entries_in_order(self):
        # docstring "insertion order", "several entries for the same header"
        h = Headers([("B", "1"), ("a", "2"), ("b", "3")])
        self.assertEqual(h.items(), [("B", "1"), ("a", "2"), ("b", "3")])

    def test_get_returns_first_match(self):
        # item 10: get = value of the first entry
        h = Headers([("Host", "h"), ("X-Id", "1"), ("x-id", "2")])
        self.assertEqual(h.get("X-ID"), "1")

    def test_get_missing_name_uses_default(self):
        # item 10
        h = Headers([("Host", "h")])
        self.assertIsNone(h.get("Date"))
        self.assertEqual(h.get("Date", "none"), "none")

    def test_get_all_order_and_type(self):
        # items 9, 10
        h = Headers([("A", "1"), ("B", "x"), ("a", "2")])
        values = h.get_all("a")
        self.assertIsInstance(values, list)
        self.assertEqual(values, ["1", "2"])
        self.assertEqual(h.get_all("missing"), [])

    def test_contains(self):
        # item 10
        h = Headers([("Content-Length", "1")])
        self.assertIn("content-LENGTH", h)
        self.assertNotIn("Content", h)

    def test_iteration_of_untouched_data(self):
        # item 10: iteration yields stored spelling, in order
        entries = [("x-lower", "1"), ("X-UPPER", "2"), ("Mixed-Case", "3"), ("x-lower", "4")]
        h = Headers(entries)
        self.assertEqual(list(h), entries)
        self.assertEqual(h.items(), entries)

    def test_items_returns_new_list(self):
        # items 9, 10
        h = Headers([("Host", "h")])
        got = h.items()
        self.assertIsInstance(got, list)
        got.append(("X", "y"))
        self.assertEqual(h.items(), [("Host", "h")])

    def test_empty_collection(self):
        # item 10
        h = Headers()
        self.assertEqual(len(h), 0)
        self.assertEqual(list(h), [])
        self.assertEqual(h.items(), [])
        self.assertIsNone(h.get("Host"))
        self.assertEqual(h.get_all("Host"), [])
        self.assertNotIn("Host", h)

    def test_set_with_same_spelling_unrelated_entries_untouched(self):
        # items 5, 6 on data the original code already handled
        h = Headers([("Host", "a"), ("Accept", "*/*"), ("Date", "d")])
        h.set("Host", "b")
        self.assertEqual(h.items(), [("Accept", "*/*"), ("Date", "d"), ("Host", "b")])

    def test_public_signatures(self):
        # item 9: public method signatures unchanged (parameter names, kinds and defaults)
        def params(fn):
            return [(p.name, p.kind, p.default) for p in inspect.signature(fn).parameters.values()]

        pk, empty = inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.empty
        self.assertEqual(params(Headers.__init__), [("self", pk, empty), ("items", pk, None)])
        self.assertEqual(params(Headers.add), [("self", pk, empty), ("name", pk, empty),
                                               ("value", pk, empty)])
        self.assertEqual(params(Headers.set), [("self", pk, empty), ("name", pk, empty),
                                               ("value", pk, empty)])
        self.assertEqual(params(Headers.get), [("self", pk, empty), ("name", pk, empty),
                                               ("default", pk, None)])
        self.assertEqual(params(Headers.get_all), [("self", pk, empty), ("name", pk, empty)])
        self.assertEqual(params(Headers.items), [("self", pk, empty)])


if __name__ == "__main__":
    unittest.main()
