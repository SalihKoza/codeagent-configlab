import dataclasses
import inspect
import unittest

import svcconfig
from svcconfig import Config, ConfigError, load_config


class PublicApiRegressionTests(unittest.TestCase):
    """Public API that must stay as it is (statement "Behavior to preserve")."""

    def test_api_exports(self):
        self.assertTrue({"Config", "ConfigError", "load_config"} <= set(svcconfig.__all__))
        self.assertTrue(callable(load_config))

    def test_api_load_config_signature(self):
        params = list(inspect.signature(load_config).parameters.values())
        self.assertEqual([p.name for p in params], ["raw"])
        self.assertEqual(params[0].kind, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        self.assertIs(params[0].default, inspect.Parameter.empty)
        self.assertEqual(load_config(raw={}), load_config({}))

    def test_api_error_type(self):
        self.assertTrue(issubclass(ConfigError, ValueError))
        with self.assertRaises(ValueError):
            load_config({"port": 0})

    def test_api_config_value_object(self):
        cfg = load_config({"tags": "a"})
        self.assertIs(type(cfg), Config)
        self.assertEqual([f.name for f in dataclasses.fields(Config)],
                         ["host", "scheme", "port", "timeout", "retries", "tags"])
        self.assertEqual(cfg, load_config({"tags": ["a"]}))
        self.assertEqual(hash(cfg), hash(load_config({"tags": ("a",)})))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            cfg.host = "x"

    def test_api_accepts_any_mapping(self):
        from types import MappingProxyType
        self.assertEqual(load_config(MappingProxyType({"port": "81"})).port, 81)


if __name__ == "__main__":
    unittest.main()
