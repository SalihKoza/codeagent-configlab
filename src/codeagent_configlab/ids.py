"""Opaque, collision-resistant identifiers.

Two distinct kinds of id exist, and they must not be conflated:

* **run id** — names one *attempt* of one experimental cell in the results store and the
  manifest. It lives outside the agent-visible boundary.
* **workspace token** — names the per-run working-copy directory the agent sees. Protocol
  §4/§9 require this path to be **opaque**: it MUST NOT encode task, configuration, or
  repetition, because the agent can read its own working-directory path. The manifest maps
  ``run_id -> (task, config, rep)`` on the harness side only.

Both are drawn from ``os.urandom`` so they never embed experimental structure. They are
deliberately different values so a leaked workspace token cannot be used to guess the run id
or vice versa.

Format:

* ``run_id``  = ``"run_" + 26 lowercase base32 chars`` (128 bits of entropy).
* ``workspace_token`` = 16 lowercase hex chars (64 bits), matching the spike convention.
"""

from __future__ import annotations

import base64
import os

RUN_ID_PREFIX = "run_"
_RUN_ID_BODY_LEN = 26  # base32 chars over 16 random bytes (128 bits), padding stripped


def new_run_id() -> str:
    """Return a fresh opaque run id like ``run_ae7k...`` (lowercase base32, no padding)."""
    raw = os.urandom(16)
    body = base64.b32encode(raw).decode("ascii").rstrip("=").lower()
    return RUN_ID_PREFIX + body[:_RUN_ID_BODY_LEN]


def new_workspace_token() -> str:
    """Return a fresh opaque 16-hex-char workspace directory token."""
    return os.urandom(8).hex()


def is_opaque(value: str, *, forbidden_substrings: tuple[str, ...] = ()) -> bool:
    """True iff *value* contains none of *forbidden_substrings* (case-insensitive).

    Used by tests to assert that an id or workspace path leaks no experimental structure
    (e.g. ``"C2"``, ``"bugfix"``, ``"rep3"`` or a task id). The check is a substring scan,
    which is sufficient because ids are random alphanumerics.
    """
    low = value.lower()
    return not any(sub.lower() in low for sub in forbidden_substrings if sub)
