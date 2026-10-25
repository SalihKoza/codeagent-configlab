import unittest

from msgheaders import Headers


class HeadersTests(unittest.TestCase):
    def test_empty(self):
        h = Headers()
        self.assertEqual(len(h), 0)
        self.assertEqual(list(h), [])
        self.assertIsNone(h.get("Host"))

    def test_constructor_keeps_order(self):
        h = Headers([("Host", "example.org"), ("Accept", "*/*")])
        self.assertEqual(h.items(), [("Host", "example.org"), ("Accept", "*/*")])

    def test_add_keeps_multiple_values(self):
        h = Headers()
        h.add("Warning", "199 a")
        h.add("Warning", "199 b")
        self.assertEqual(h.get_all("Warning"), ["199 a", "199 b"])
        self.assertEqual(len(h), 2)

    def test_get_is_case_insensitive(self):
        h = Headers([("Content-Length", "12")])
        self.assertEqual(h.get("content-length"), "12")
        self.assertIn("CONTENT-LENGTH", h)

    def test_get_default(self):
        self.assertEqual(Headers().get("Host", "none"), "none")

    def test_iteration_keeps_stored_spelling(self):
        h = Headers([("x-custom", "1"), ("Date", "today")])
        self.assertEqual(list(h), [("x-custom", "1"), ("Date", "today")])

    def test_set_replaces_existing_value(self):
        h = Headers([("Host", "a"), ("Accept", "*/*")])
        h.set("Host", "b")
        self.assertEqual(h.items(), [("Accept", "*/*"), ("Host", "b")])

    def test_set_new_header_appends(self):
        h = Headers([("Host", "a")])
        h.set("Accept", "*/*")
        self.assertEqual(h.items(), [("Host", "a"), ("Accept", "*/*")])


if __name__ == "__main__":
    unittest.main()
