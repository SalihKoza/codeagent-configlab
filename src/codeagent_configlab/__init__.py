"""CodeAgent ConfigLab — minimal benchmark harness skeleton (V0).

This package is the *orchestration* layer for the experiment defined in
``docs/EXPERIMENT_PROTOCOL_V0.md``. It is deliberately small: it can represent and
execute future **pilot** runs safely, but it contains no final benchmark task and does
not run the 54-run campaign.

Design rules baked into the code:

* The protocol is the source of truth. Status axes and artifact groups mirror
  protocol §6/§7 rather than inventing a parallel vocabulary.
* Stdlib only — no third-party dependency, so it runs as ``cclab`` in WSL with no pip.
* Immutable specification (:class:`~codeagent_configlab.manifest.RunManifest`) is kept
  logically separate from observed output (:class:`~codeagent_configlab.result.RunResult`);
  runtime results never mutate the spec.
* No secret value is ever represented, stored, or emitted.
"""

__version__ = "0.0.1"

# Bump when the manifest/result schema shape changes in a backward-incompatible way.
SCHEMA_VERSION = "run-manifest/v0"
RESULT_SCHEMA_VERSION = "run-result/v0"

from .sentinels import OPEN, NA, is_open, is_na  # noqa: E402,F401

__all__ = ["__version__", "SCHEMA_VERSION", "RESULT_SCHEMA_VERSION", "OPEN", "NA", "is_open", "is_na"]
