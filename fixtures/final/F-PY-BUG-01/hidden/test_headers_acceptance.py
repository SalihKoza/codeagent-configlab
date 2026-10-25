import unittest

from msgheaders import Headers


class SetAcceptanceTests(unittest.TestCase):
    """Statement "Required behavior of set(name, value)" items 1-7 (+ 8-10 where set is involved)."""

    def test_single_match_different_case(self):
        # items 1, 2, 3, 4: one variant spelled differently is replaced; new spelling kept
        h = Headers([("Content-Type", "text/plain")])
        h.set("content-type", "application/json")
        self.assertEqual(h.items(), [("content-type", "application/json")])

    def test_statement_example(self):
        # "Bug report" expected result
        h = Headers([("Content-Type", "text/plain"), ("CONTENT-TYPE", "text/html")])
        h.set("content-type", "application/json")
        self.assertEqual(h.items(), [("content-type", "application/json")])
        self.assertEqual(h.get("Content-Type"), "application/json")

    def test_several_case_variants(self):
        # item 2: all matches regardless of spelling and count; item 3: exactly one remains
        h = Headers([("Cache-Control", "a"), ("CACHE-CONTROL", "b"), ("cache-CONTROL", "c"),
                     ("cache-control", "d")])
        h.set("Cache-control", "no-store")
        self.assertEqual(h.items(), [("Cache-control", "no-store")])

    def test_exact_case_duplicates(self):
        # item 2: "how many there are"; item 3
        h = Headers([("Accept", "a"), ("Accept", "b"), ("Accept", "c")])
        h.set("Accept", "d")
        self.assertEqual(h.items(), [("Accept", "d")])

    def test_exact_duplicates_mixed_with_variants(self):
        # items 1, 2, 3, 4
        h = Headers([("X-Tag", "1"), ("x-tag", "2"), ("X-Tag", "3"), ("X-TAG", "4")])
        h.set("X-Tag", "5")
        self.assertEqual(h.items(), [("X-Tag", "5")])

    def test_mixture_keeps_non_matching_order(self):
        # items 2, 5, 6: interleaved non-matching entries (incl. their own duplicates) keep order
        h = Headers([("Via", "1.0 a"), ("X-Trace", "1"), ("Host", "h"), ("x-trace", "2"),
                     ("Via", "1.1 b"), ("Date", "d"), ("X-TRACE", "3"), ("via", "1.1 c")])
        h.set("x-Trace", "9")
        self.assertEqual(h.items(), [("Via", "1.0 a"), ("Host", "h"), ("Via", "1.1 b"),
                                     ("Date", "d"), ("via", "1.1 c"), ("x-Trace", "9")])

    def test_no_match_appends(self):
        # item 7
        h = Headers([("Host", "h"), ("Date", "d")])
        h.set("Accept", "*/*")
        self.assertEqual(h.items(), [("Host", "h"), ("Date", "d"), ("Accept", "*/*")])

    def test_no_match_keeps_interleaved_order(self):
        # items 6, 7: nothing matches, so every existing entry stays exactly where it was
        h = Headers([("Via", "1"), ("Host", "h"), ("via", "2"), ("Date", "d"), ("VIA", "3")])
        h.set("Accept", "*/*")
        self.assertEqual(h.items(), [("Via", "1"), ("Host", "h"), ("via", "2"), ("Date", "d"),
                                     ("VIA", "3"), ("Accept", "*/*")])

    def test_set_on_empty_collection(self):
        # item 7
        h = Headers()
        h.set("ETag", "x1")
        self.assertEqual(h.items(), [("ETag", "x1")])

    def test_replacement_spelling_is_argument(self):
        # item 4: stored spelling is exactly the argument, not an old spelling or a normalized one
        h = Headers([("CONTENT-length", "1")])
        h.set("cOnTeNt-LeNgTh", "2")
        self.assertEqual([n for n, _ in h], ["cOnTeNt-LeNgTh"])

    def test_replacement_moves_to_end(self):
        # item 5: old match was first; the new entry goes to the end
        h = Headers([("Server", "s1"), ("Host", "h"), ("Date", "d")])
        h.set("SERVER", "s2")
        self.assertEqual(h.items(), [("Host", "h"), ("Date", "d"), ("SERVER", "s2")])

    def test_prefix_name_is_not_a_match(self):
        # statement intro: "Accept" and "Accept-Encoding" do not match; item 6
        h = Headers([("accept-encoding", "gzip"), ("ACCEPT", "a"), ("Accept-Language", "en")])
        h.set("Accept", "*/*")
        self.assertEqual(h.items(), [("accept-encoding", "gzip"), ("Accept-Language", "en"),
                                     ("Accept", "*/*")])

    def test_lookup_after_set_in_other_case(self):
        # item 10: lookups observe the corrected state
        h = Headers([("Set-Cookie", "a=1"), ("Host", "h"), ("SET-COOKIE", "b=2")])
        h.set("set-cookie", "c=3")
        self.assertEqual(h.get("SET-cookie"), "c=3")
        self.assertEqual(h.get_all("Set-Cookie"), ["c=3"])
        self.assertIn("SET-COOKIE", h)
        self.assertEqual(len(h), 2)

    def test_repeated_set_with_different_case(self):
        # items 2, 3, 4
        h = Headers([("Host", "h")])
        h.set("Location", "/a")
        h.set("LOCATION", "/b")
        h.set("location", "/c")
        self.assertEqual(h.items(), [("Host", "h"), ("location", "/c")])

    def test_add_after_set_still_allows_multiple_values(self):
        # item 8: add unchanged, may create entries differing only in case
        h = Headers([("Link", "<a>"), ("LINK", "<b>")])
        h.set("link", "<c>")
        h.add("Link", "<d>")
        h.add("LINK", "<e>")
        self.assertEqual(h.items(), [("link", "<c>"), ("Link", "<d>"), ("LINK", "<e>")])
        self.assertEqual(h.get_all("link"), ["<c>", "<d>", "<e>"])

    def test_set_returns_none(self):
        # item 9
        h = Headers([("Host", "a"), ("HOST", "b")])
        self.assertIsNone(h.set("host", "c"))


if __name__ == "__main__":
    unittest.main()
