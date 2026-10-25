import unittest

from svcconfig import Config, ConfigError, load_config

DEFAULTS = dict(host="localhost", scheme="http", port=80, timeout=30.0, retries=3, tags=())


def cfg(**overrides):
    return Config(**{**DEFAULTS, **overrides})


class BehaviorCase(unittest.TestCase):
    """Every expectation below is stated in the ``load_config`` docstring (quoted in the task
    statement); only the public loader is called."""

    def rejects(self, raw, message):
        with self.assertRaises(ConfigError, msg=f"raw={raw!r}") as ctx:
            load_config(raw)
        self.assertEqual(str(ctx.exception), message, f"raw={raw!r}")


class ValuesAndDefaultsTests(BehaviorCase):
    def test_behavior_full_valid_settings(self):
        # every setting given in its native form
        self.assertEqual(
            load_config({"host": "db.internal", "scheme": "https", "port": 8443, "timeout": 12.5,
                         "retries": 0, "tags": ["blue", "green"]}),
            cfg(host="db.internal", scheme="https", port=8443, timeout=12.5, retries=0,
                tags=("blue", "green")))

    def test_behavior_every_default(self):
        # each setting's default
        self.assertEqual(load_config({}), cfg())

    def test_behavior_none_is_omitted(self):
        # "A setting whose value is None is treated as omitted"
        self.assertEqual(load_config(dict.fromkeys(DEFAULTS)), cfg())
        self.assertEqual(load_config({"scheme": "https", "port": None}), cfg(scheme="https", port=443))

    def test_behavior_default_port_follows_normalized_scheme(self):
        # port default: 443 if the (normalized) scheme is https, otherwise 80
        self.assertEqual(load_config({"scheme": " HTTPS "}), cfg(scheme="https", port=443))
        self.assertEqual(load_config({"scheme": "Http"}).port, 80)

    def test_behavior_explicit_port_wins_over_default(self):
        self.assertEqual(load_config({"scheme": "https", "port": "8443"}),
                         cfg(scheme="https", port=8443))
        self.assertEqual(load_config({"port": 443}), cfg(port=443))

    def test_behavior_input_mapping_not_modified(self):
        # "raw itself is never modified"
        raw = {"host": " A.B ", "tags": ["X", "x"], "port": "81", "scheme": None}
        before = {"host": " A.B ", "tags": ["X", "x"], "port": "81", "scheme": None}
        load_config(raw)
        self.assertEqual(raw, before)


class CoercionTests(BehaviorCase):
    def test_behavior_port_forms(self):
        # int, or ASCII digits optionally surrounded by whitespace
        self.assertEqual(load_config({"port": " 8080 "}).port, 8080)
        self.assertEqual(load_config({"port": "\t65535\n"}).port, 65535)
        self.assertEqual(load_config({"port": 1}).port, 1)

    def test_behavior_port_rejected_forms(self):
        # anything else -> "port must be an integer" (bool not accepted)
        for bad in ("+80", "-1", "8_0", "80.0", "", "  ", "８０", 8080.0, True, b"80", [80]):
            self.rejects({"port": bad}, "port must be an integer")

    def test_behavior_retries_forms(self):
        # same accepted forms as port
        self.assertEqual(load_config({"retries": " 7 "}).retries, 7)
        self.assertEqual(load_config({"retries": 0}).retries, 0)
        for bad in ("+1", "1.0", "", False, 2.0, "two"):
            self.rejects({"retries": bad}, "retries must be an integer")

    def test_behavior_timeout_forms(self):
        # int/float (not bool) or a string float() accepts after stripping; stored as float
        t = load_config({"timeout": 5}).timeout
        self.assertEqual(t, 5.0)
        self.assertIs(type(t), float)
        self.assertEqual(load_config({"timeout": " 2.5 "}).timeout, 2.5)
        self.assertEqual(load_config({"timeout": "1e2"}).timeout, 100.0)
        self.assertEqual(load_config({"timeout": 0.5}).timeout, 0.5)
        for bad in ("abc", "", "1,5", True, [1], b"2"):
            self.rejects({"timeout": bad}, "timeout must be a number")

    def test_behavior_text_settings_must_be_strings(self):
        self.rejects({"host": 42}, "host must be a string")
        self.rejects({"scheme": b"http"}, "scheme must be a string")

    def test_behavior_tags_forms(self):
        # comma-separated string, list or tuple of strings; stored as a tuple
        self.assertEqual(load_config({"tags": "a,b"}).tags, ("a", "b"))
        self.assertEqual(load_config({"tags": ("a", "b")}).tags, ("a", "b"))
        self.assertEqual(load_config({"tags": ["a"]}).tags, ("a",))
        self.assertEqual(load_config({"tags": ""}).tags, ())
        self.assertEqual(load_config({"tags": []}).tags, ())
        for bad in (5, ["a", 1], {"a"}, ("a", None)):
            self.rejects({"tags": bad}, "tags must be a string or a list of strings")


class NormalizationTests(BehaviorCase):
    def test_behavior_host_normalization(self):
        self.assertEqual(load_config({"host": "  API.Example.ORG "}).host, "api.example.org")

    def test_behavior_scheme_normalization(self):
        self.assertEqual(load_config({"scheme": "  hTTp\t"}).scheme, "http")

    def test_behavior_tags_normalization(self):
        # strip, lower-case, drop empties, keep repeats only at their first position
        self.assertEqual(load_config({"tags": " Blue,green ,,BLUE, red ,Green,"}).tags,
                         ("blue", "green", "red"))
        self.assertEqual(load_config({"tags": ["B", " a", "b", "  "]}).tags, ("b", "a"))

    def test_behavior_tags_limit_counts_normalized_tags(self):
        # "At most 5 tags after this normalization"
        self.assertEqual(len(load_config({"tags": "a,b,c,d,e,A,B, ,"}).tags), 5)
        self.rejects({"tags": "a,b,c,d,e,f"}, "at most 5 tags allowed")
        self.rejects({"tags": ["a", "b", "c", "d", "e", "F"]}, "at most 5 tags allowed")


class ValueRuleTests(BehaviorCase):
    def test_behavior_empty_host(self):
        self.rejects({"host": ""}, "host must not be empty")
        self.rejects({"host": "  \t"}, "host must not be empty")

    def test_behavior_scheme_allowed_values(self):
        for bad in ("ftp", "", " ", "https:", "http s"):
            self.rejects({"scheme": bad}, "scheme must be one of: http, https")

    def test_behavior_port_range(self):
        self.assertEqual(load_config({"port": "1"}).port, 1)
        self.assertEqual(load_config({"port": 65535}).port, 65535)
        for bad in (0, "0", 65536, "65536", -1):
            self.rejects({"port": bad}, "port must be between 1 and 65535")

    def test_behavior_timeout_range(self):
        self.assertEqual(load_config({"timeout": 300, "retries": 1}).timeout, 300.0)
        self.assertEqual(load_config({"timeout": "0.001"}).timeout, 0.001)
        for bad in (0, "0", -1.5, 300.0001, "301"):
            self.rejects({"timeout": bad}, "timeout must be greater than 0 and at most 300")

    def test_behavior_retries_range(self):
        self.assertEqual(load_config({"retries": "10", "timeout": 10}).retries, 10)
        for bad in (11, "11", -1):
            self.rejects({"retries": bad}, "retries must be between 0 and 10")


class CrossRuleTests(BehaviorCase):
    def test_behavior_https_cannot_use_port_80(self):
        self.rejects({"scheme": "https", "port": 80}, "https cannot use port 80")
        self.rejects({"scheme": " HTTPS", "port": " 80"}, "https cannot use port 80")
        self.assertEqual(load_config({"scheme": "http", "port": 80}), cfg())
        self.assertEqual(load_config({"scheme": "https", "port": 443}), cfg(scheme="https", port=443))

    def test_behavior_retry_budget(self):
        # timeout * (retries + 1) must not exceed 600 (600 itself is allowed)
        self.assertEqual(load_config({"timeout": 300, "retries": 1}).retries, 1)
        self.assertEqual(load_config({"timeout": 60, "retries": 9}).timeout, 60.0)
        self.rejects({"timeout": 300, "retries": 2}, "timeout * (retries + 1) must not exceed 600")
        self.rejects({"timeout": 200}, "timeout * (retries + 1) must not exceed 600")
        self.rejects({"timeout": "60.5", "retries": "9"},
                     "timeout * (retries + 1) must not exceed 600")


class PrecedenceTests(BehaviorCase):
    """Docstring: unknown setting; then wrong type/form in setting order; then value/range in
    setting order; then the rules between settings (in their listed order)."""

    def test_behavior_unknown_setting_first(self):
        self.rejects({"port": "x", "zone": "eu"}, "unknown setting: zone")
        self.rejects({"Host": "a"}, "unknown setting: Host")

    def test_behavior_alphabetically_first_unknown(self):
        self.rejects({"zeta": 1, "alpha": 2, "mid": 3}, "unknown setting: alpha")

    def test_behavior_form_errors_in_setting_order(self):
        self.rejects({"tags": 5, "retries": "x", "timeout": "x", "port": "x", "scheme": 1,
                      "host": 1}, "host must be a string")
        self.rejects({"tags": 5, "retries": "x", "timeout": "x", "port": "x", "scheme": 1},
                     "scheme must be a string")
        self.rejects({"tags": 5, "retries": "x", "timeout": "x", "port": "x"},
                     "port must be an integer")
        self.rejects({"tags": 5, "retries": "x", "timeout": "x"}, "timeout must be a number")
        self.rejects({"tags": 5, "retries": "x"}, "retries must be an integer")

    def test_behavior_form_error_before_earlier_value_error(self):
        # a form error of a later setting beats a value error of an earlier setting
        self.rejects({"host": "", "scheme": "ftp", "tags": 5},
                     "tags must be a string or a list of strings")
        self.rejects({"scheme": "ftp", "port": "x"}, "port must be an integer")

    def test_behavior_value_errors_in_setting_order(self):
        bad = {"host": " ", "scheme": "ftp", "port": 0, "timeout": 0, "retries": 11,
               "tags": "a,b,c,d,e,f"}
        order = ["host must not be empty", "scheme must be one of: http, https",
                 "port must be between 1 and 65535",
                 "timeout must be greater than 0 and at most 300",
                 "retries must be between 0 and 10", "at most 5 tags allowed"]
        for key, message in zip(list(bad), order):
            self.rejects(bad, message)
            del bad[key]

    def test_behavior_value_error_before_cross_rules(self):
        self.rejects({"scheme": "https", "port": 80, "retries": 11},
                     "retries must be between 0 and 10")
        self.rejects({"scheme": "https", "port": 80, "timeout": 300, "retries": 5},
                     "https cannot use port 80")


if __name__ == "__main__":
    unittest.main()
