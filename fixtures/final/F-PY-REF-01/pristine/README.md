# svcconfig

Loads a service configuration from raw key/value settings (for example read from a file or the
environment) into an immutable `Config`. `load_config(raw)` coerces the raw values, fills in
defaults, normalizes them and validates the result; every problem is reported as `ConfigError`.
The accepted forms, defaults, rules and error messages are documented in the `load_config`
docstring (`svcconfig/loader.py`).

Run the public tests:

    python3 -m unittest tests.test_loader -v
