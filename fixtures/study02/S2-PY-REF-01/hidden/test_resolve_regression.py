"""Hidden acceptance tests for S2-PY-REF-01: Layer structure refactor.

Re-exercises resolve/set_override/layers() behavior, plus a case using layer names that do
NOT sort alphabetically into precedence order (to defeat a refactor that silently reorders
layers by name instead of preserving the original precedence order).
"""

import sys
import unittest

import configmerge  # noqa: F401 - ensures the package (and its submodules) is initialized
from configmerge import resolve, set_override

layers = sys.modules["configmerge.layers"]


class RegressionTests(unittest.TestCase):
    def setUp(self):
        layers.clear_layers()

    def test_multi_layer_key_collision(self):
        layers.add_layer("base", {"service": {"timeout": 10}}, precedence=0)
        layers.add_layer("env", {"service": {"timeout": 20}}, precedence=1)
        self.assertEqual(resolve("service.timeout"), 20)

    def test_dotted_path_nesting(self):
        layers.add_layer("base", {"a": {"b": {"c": 5}}}, precedence=0)
        self.assertEqual(resolve("a.b.c"), 5)

    def test_override_precedence(self):
        layers.add_layer("base", {"x": 1}, precedence=0)
        set_override("x", 42)
        self.assertEqual(resolve("x"), 42)

    def test_non_alphabetical_layer_names_preserve_precedence_order(self):
        # Layer names deliberately do NOT sort alphabetically into precedence order:
        # "zz-base" has the lowest precedence, "aa-env" has the highest (before override).
        layers.add_layer("zz-base", {"x": "from-base"}, precedence=0)
        layers.add_layer("aa-env", {"x": "from-env"}, precedence=1)
        # If a refactor silently reorders layers by name instead of preserving the
        # original precedence order, "aa-env" would sort before "zz-base" alphabetically
        # and this resolve() would incorrectly return "from-base" (using the wrong
        # most-specific layer).
        self.assertEqual(resolve("x"), "from-env")


if __name__ == "__main__":
    unittest.main()
