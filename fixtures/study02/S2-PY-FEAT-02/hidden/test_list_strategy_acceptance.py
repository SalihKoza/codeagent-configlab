"""Hidden acceptance tests for S2-PY-FEAT-02: list_strategy option."""

import sys
import unittest

import configmerge  # noqa: F401 - ensures the package (and its submodules) is initialized
from configmerge import resolve

layers = sys.modules["configmerge.layers"]


class ListStrategyTests(unittest.TestCase):
    def setUp(self):
        layers.clear_layers()

    def test_replace_default_unchanged_for_scalars(self):
        layers.add_layer("base", {"name": "base-svc"}, precedence=0)
        layers.add_layer("env", {"name": "env-svc"}, precedence=1)
        self.assertEqual(resolve("name"), "env-svc")
        self.assertEqual(resolve("name", list_strategy="replace"), "env-svc")

    def test_append_with_three_layers_preserves_least_to_most_specific_order(self):
        layers.add_layer("base", {"plugins": ["base-a", "base-b"]}, precedence=0)
        layers.add_layer("env", {"plugins": ["env-a"]}, precedence=1)
        layers.add_layer("override", {"plugins": ["override-a"]}, precedence=2)
        result = resolve("plugins", list_strategy="append")
        self.assertEqual(result, ["base-a", "base-b", "env-a", "override-a"])

    def test_append_on_non_list_key_behaves_as_replace(self):
        layers.add_layer("base", {"name": "base-svc"}, precedence=0)
        layers.add_layer("env", {"name": "env-svc"}, precedence=1)
        self.assertEqual(resolve("name", list_strategy="append"), "env-svc")


if __name__ == "__main__":
    unittest.main()
