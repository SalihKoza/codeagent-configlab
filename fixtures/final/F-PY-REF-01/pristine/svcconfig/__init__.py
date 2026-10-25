"""svcconfig — load and validate a small service configuration."""

from .loader import Config, ConfigError, load_config

__all__ = ["Config", "ConfigError", "load_config"]
