import sys
import unittest

import configmerge  # noqa: F401 - ensures the package (and its submodules) is initialized

layers = sys.modules["configmerge.layers"]


class LayerStackTests(unittest.TestCase):
    def setUp(self):
        layers.clear_layers()

    def test_layers_returned_least_to_most_specific(self):
        layers.add_layer("base", {"a": 1}, precedence=0)
        layers.add_layer("env", {"a": 2}, precedence=1)
        names = [layer["name"] for layer in layers.layers()]
        self.assertEqual(names, ["base", "env"])

    def test_dotted_path_nesting(self):
        layers.add_layer("base", {"a": {"b": {"c": 5}}}, precedence=0)
        found = layers.get_dotted(layers.layers()[0]["data"], "a.b.c")
        self.assertEqual(found, (5, True))


if __name__ == "__main__":
    unittest.main()
