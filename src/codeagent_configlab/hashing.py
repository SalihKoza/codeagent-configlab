"""Deterministic SHA-256 hashing helpers for bytes, files, and working-copy trees.

The working-copy tree hash mirrors the algorithm used in the spikes
(``spike/harness-readiness/spike.sh`` ``wc_hash``): every regular file's content is hashed,
paths are sorted with a stable (byte-wise) collation, and generated caches are excluded via a
frozen ignore list. This is the primitive behind:

* the pristine-fixture baseline hash (protocol §4);
* the C2 phase-1 read-only check (§8): tree hash before == after.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterable

# Generated caches excluded from tree hashing and diffs (protocol §4). This list MUST NOT
# hide source or test files. Extend per-language when tasks are frozen (O9), not here.
DEFAULT_IGNORE_DIRS = ("__pycache__", ".pytest_cache", "node_modules", ".git")


def sha256_bytes(data: bytes) -> str:
    """Hex SHA-256 of *data*."""
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    """Hex SHA-256 of *text* encoded as UTF-8 (used for statement/CLAUDE.md/wrapper hashes)."""
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: os.PathLike | str) -> str:
    """Hex SHA-256 of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_tree_files(root: Path, ignore_dirs: Iterable[str]) -> list[Path]:
    ignore = set(ignore_dirs)
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # prune ignored directories in place so os.walk does not descend into them
        dirnames[:] = [d for d in dirnames if d not in ignore]
        for name in filenames:
            out.append(Path(dirpath) / name)
    return out


def tree_hash(root: os.PathLike | str, ignore_dirs: Iterable[str] = DEFAULT_IGNORE_DIRS) -> str:
    """Deterministic hash of a directory tree's file contents.

    Each file contributes ``"<relative/posix/path>\\0<sha256-of-content>\\n"`` to a running
    digest; entries are sorted by relative POSIX path with C collation (bytewise) so the
    result is stable across machines and filesystems. ``.git`` and generated caches are
    excluded by default. Empty directories do not affect the hash.
    """
    root = Path(root)
    entries: list[tuple[bytes, str]] = []
    for f in _iter_tree_files(root, ignore_dirs):
        rel = f.relative_to(root).as_posix()
        entries.append((rel.encode("utf-8"), sha256_file(f)))
    entries.sort(key=lambda e: e[0])  # bytewise (LC_ALL=C-equivalent) sort
    h = hashlib.sha256()
    for rel_bytes, digest in entries:
        h.update(rel_bytes)
        h.update(b"\x00")
        h.update(digest.encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def canonical_json_hash(obj: object) -> str:
    """Hash of an object's canonical JSON (sorted keys, compact separators).

    Used for policy/settings/envelope identity hashes recorded in the manifest (§13). The
    caller is responsible for ensuring *obj* contains no secret values.
    """
    import json

    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_text(canonical)
