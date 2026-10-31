import sys
import unittest

import configmerge  # noqa: F401 - ensures the package (and its submodules) is initialized
from configmerge import resolve, set_override

layers = sys.modules["configmerge.layers"]


class ResolveTests(unittest.TestCase):
    def setUp(self):
        layers.clear_layers()
        layers.add_layer("base", {"service": {"timeout": 10}, "name": "base-svc"}, precedence=0)
        layers.add_layer("env", {"service": {"timeout": 20}}, precedence=1)

    def test_most_specific_wins_for_scalar(self):
        self.assertEqual(resolve("service.timeout"), 20)

    def test_falls_back_to_less_specific_layer(self):
        self.assertEqual(resolve("name"), "base-svc")

    def test_missing_key_returns_none(self):
        self.assertIsNone(resolve("does.not.exist"))

    def test_set_override_wins_over_everything(self):
        set_override("service.timeout", 99)
        self.assertEqual(resolve("service.timeout"), 99)


if __name__ == "__main__":
    unittest.main()
