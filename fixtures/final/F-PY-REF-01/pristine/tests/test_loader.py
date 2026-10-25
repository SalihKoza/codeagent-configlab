import unittest

from svcconfig import Config, ConfigError, load_config


class LoadConfigTests(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(load_config({}),
                         Config(host="localhost", scheme="http", port=80, timeout=30.0,
                                retries=3, tags=()))

    def test_string_values_are_coerced(self):
        cfg = load_config({"host": "API.example.org", "port": "8080", "timeout": "12.5",
                           "retries": "2", "tags": "blue, Green"})
        self.assertEqual(cfg, Config(host="api.example.org", scheme="http", port=8080,
                                     timeout=12.5, retries=2, tags=("blue", "green")))

    def test_https_default_port(self):
        self.assertEqual(load_config({"scheme": "https"}).port, 443)

    def test_none_means_omitted(self):
        self.assertEqual(load_config({"port": None, "tags": None}), load_config({}))

    def test_bad_port_form(self):
        with self.assertRaises(ConfigError) as ctx:
            load_config({"port": "eighty"})
        self.assertEqual(str(ctx.exception), "port must be an integer")

    def test_port_out_of_range(self):
        with self.assertRaises(ConfigError) as ctx:
            load_config({"port": 70000})
        self.assertEqual(str(ctx.exception), "port must be between 1 and 65535")

    def test_unknown_setting(self):
        with self.assertRaises(ConfigError) as ctx:
            load_config({"colour": "red"})
        self.assertEqual(str(ctx.exception), "unknown setting: colour")

    def test_config_is_immutable(self):
        cfg = load_config({})
        with self.assertRaises(AttributeError):
            cfg.port = 1


if __name__ == "__main__":
    unittest.main()
