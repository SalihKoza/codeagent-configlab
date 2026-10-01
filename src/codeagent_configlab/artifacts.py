"""Per-run artifact capture with an allowlist and a secret-safety scanner (protocol §7/§18/§19).

Artifacts live in ``<results_root>/<run_id>/`` which is **outside** the agent-visible boundary.
Only allowlisted artifact names are written. A secret scanner refuses to persist content that
contains known secret markers (token prefixes, the fake canary marker, credential filenames, or
any sanitized auth-variable value). No credential file is ever copied.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# The only artifact file names the store will write (protocol §7). Anything else is rejected.
ARTIFACT_ALLOWLIST = frozenset(
    {
        "manifest.json",
        "result.json",
        "preflight.json",
        "stdout.txt",
        "stderr.txt",
        "events.jsonl",
        "final.diff",
        "changed_files.json",
        "evaluator.json",
        "cleanup.json",
        "process.json",
        "phase1.events.jsonl",
        "phase2.events.jsonl",
        "plan.txt",
        # C2 per-phase evidence (G2) and treatment provenance (G9)
        "phase1.stdout.txt",
        "phase1.stderr.txt",
        "phase1.process.json",
        "phase2.stdout.txt",
        "phase2.stderr.txt",
        "phase2.process.json",
        "c2.json",
        "treatment.json",
        # neutral baseline + agent start/final state identity (G6/G7)
        "baseline.json",
        "start_state.json",
        "final_state.json",
        # G12: what was withheld / could not be written, as safe metadata
        "artifact_report.json",
        # G10: evaluator re-runs on the preserved final state (never rewrites result.json)
        "reevaluation.json",
    }
)

# G12 reason codes (never the matched marker, never an exception message).
CONTENT_WITHHELD = "content_withheld:secret_policy"
WRITE_FAILED = "artifact_write_failed"
SERIALIZATION_FAILED = "artifact_serialization_failed"
WITHHELD_VALUE = "[withheld: secret-scan marker; {n} bytes]"
WITHHELD_FILE = "[content withheld: " + CONTENT_WITHHELD + "; {n} bytes; see artifact_report.json]\n"

# Static secret markers that must never appear in any artifact. ``sk-ant-`` catches API keys;
# ``.credentials.json`` catches a credential-file copy path; ``CREDSPIKE`` / ``CRED2-`` catch the
# spike fake canaries. Real token values are never known to the harness and never searched for.
STATIC_SECRET_MARKERS = ("sk-ant-", ".credentials.json", "CREDSPIKE-CANARY", "CRED2-CANARY", "CRED2-PWN")


class ArtifactSecretError(ValueError):
    """Raised when artifact content contains a forbidden secret marker."""


class ArtifactNameError(ValueError):
    """Raised when an artifact name is not on the allowlist."""


class ArtifactFinalizationError(RuntimeError):
    """A required run record (result/manifest) could not be persisted at all (G12).

    Raised only after cleanup has run; its message never contains artifact content.
    """


def withhold_markers(obj, markers: Iterable[str] = (), *, keys: bool = False):
    """Copy of a JSON-like object with every string that trips the secret scan replaced by a
    size-only placeholder (G8/G12). With ``keys=True`` offending dict keys are replaced too.
    No hash of withheld content is ever computed. The scanner itself is never weakened.
    """
    if isinstance(obj, dict):
        out = {}
        for i, (k, v) in enumerate(obj.items()):
            if keys and isinstance(k, str) and scan_for_secrets(k, markers):
                k = f"[withheld key {i}: secret-scan marker; {len(k.encode('utf-8'))} bytes]"
            out[k] = withhold_markers(v, markers, keys=keys)
        return out
    if isinstance(obj, (list, tuple)):
        return [withhold_markers(v, markers, keys=keys) for v in obj]
    if isinstance(obj, str) and scan_for_secrets(obj, markers):
        return WITHHELD_VALUE.format(n=len(obj.encode("utf-8")))
    return obj


def scan_for_secrets(text: str, extra_markers: Iterable[str] = ()) -> list[str]:
    """Return the list of forbidden markers found in *text* (empty == clean).

    ``extra_markers`` lets a caller add run-specific markers (e.g. a fake canary, or the values
    of sanitized auth env vars) without those markers being stored anywhere.
    """
    found = []
    for marker in (*STATIC_SECRET_MARKERS, *[m for m in extra_markers if m]):
        if marker and marker in text:
            found.append(marker)
    return found


@dataclass
class ArtifactStore:
    """Filesystem home for one run's artifacts."""

    run_dir: Path
    extra_secret_markers: tuple[str, ...] = ()
    # G12: one entry per write_safe() call that did not simply write the content.
    report: list = field(default_factory=list)

    @classmethod
    def create(cls, results_root: Path | str, run_id: str, extra_secret_markers: Iterable[str] = ()) -> "ArtifactStore":
        run_dir = Path(results_root) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return cls(run_dir=run_dir, extra_secret_markers=tuple(extra_secret_markers))

    def _check_name(self, name: str) -> None:
        if name not in ARTIFACT_ALLOWLIST:
            raise ArtifactNameError(f"artifact name not allowlisted: {name!r}")

    def write_text(self, name: str, text: str) -> Path:
        """Write a text artifact after allowlist + secret checks. Returns the path."""
        self._check_name(name)
        leaks = scan_for_secrets(text, self.extra_secret_markers)
        if leaks:
            # never echo the matched markers: extra markers may be real sanitized secret values
            raise ArtifactSecretError(f"refusing to write {name}: {CONTENT_WITHHELD} "
                                      f"({len(leaks)} rule(s))")
        path = self.run_dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def write_json(self, name: str, obj: object) -> Path:
        return self.write_text(name, json.dumps(obj, indent=2, ensure_ascii=False))

    # ------------------------------------------------------------------ G12 ----
    def write_safe(self, name: str, content) -> dict:
        """Write an artifact without ever raising for content or storage problems (G12).

        * clean content -> written as-is (``written``);
        * scanner refusal -> the content is NOT stored. JSON (dict/list) and ``.jsonl`` artifacts
          keep their structure with offending strings/keys replaced (``fields_withheld``); plain
          text becomes a placeholder file (``content_withheld``). The file always exists, so a
          withheld artifact is never mistaken for one that was never produced;
        * storage failure (``OSError``) -> ``write_failed`` / ``artifact_write_failed``;
          serialization failure -> ``write_failed`` / ``artifact_serialization_failed``.
        Only the exception class is recorded, never its message. Returns the report entry.
        """
        self._check_name(name)
        markers = self.extra_secret_markers
        entry = {"name": name, "status": "written", "reason": None, "size_bytes": None,
                 "content_withheld": False}
        try:
            if isinstance(content, (dict, list)):
                text = json.dumps(content, indent=2, ensure_ascii=False)
            else:
                text = str(content)
        except (TypeError, ValueError) as exc:
            entry.update(status="write_failed", reason=SERIALIZATION_FAILED, error_type=type(exc).__name__)
            self.report.append(entry)
            return entry
        try:
            if not scan_for_secrets(text, markers):
                self.write_text(name, text)
                return entry
            entry.update(content_withheld=True, reason=CONTENT_WITHHELD,
                         size_bytes=len(text.encode("utf-8")))
            if isinstance(content, (dict, list)):
                safe = json.dumps(withhold_markers(content, markers, keys=True), indent=2,
                                  ensure_ascii=False)
                entry["status"] = "fields_withheld"
            elif name.endswith(".jsonl"):
                lines = []
                for line in text.splitlines():
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        obj = None
                    if obj is None:
                        lines.append(line if not scan_for_secrets(line, markers) else json.dumps(
                            {"type": "cclab_line_withheld", "reason": CONTENT_WITHHELD,
                             "size_bytes": len(line.encode("utf-8"))}))
                    else:
                        lines.append(json.dumps(withhold_markers(obj, markers, keys=True)))
                safe = "\n".join(lines)
                entry["status"] = "fields_withheld"
            else:
                safe = WITHHELD_FILE.format(n=entry["size_bytes"])
                entry["status"] = "content_withheld"
            try:
                self.write_text(name, safe)
            except ArtifactSecretError:   # structure itself still trips the scan: whole placeholder
                self.write_text(name, WITHHELD_FILE.format(n=entry["size_bytes"]))
                entry["status"] = "content_withheld"
        except OSError as exc:
            entry.update(status="write_failed", reason=WRITE_FAILED, error_type=type(exc).__name__)
        self.report.append(entry)
        return entry

    def write_failures(self) -> list[str]:
        return [e["name"] for e in self.report if e["status"] == "write_failed"]

    def ref(self, name: str) -> str:
        """Relative logical reference stored in the result document (never an absolute path)."""
        return name

    def scan_dir_for_secrets(self, extra_markers: Iterable[str] = ()) -> dict[str, list[str]]:
        """Scan every file already in the run dir; return {relpath: [markers]} for any leaks."""
        markers = (*self.extra_secret_markers, *extra_markers)
        out: dict[str, list[str]] = {}
        for f in self.run_dir.rglob("*"):
            if not f.is_file():
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            leaks = scan_for_secrets(text, markers)
            if leaks:
                out[f.relative_to(self.run_dir).as_posix()] = leaks
        return out


def schema_has_no_secret_fields(schema: dict) -> Optional[str]:
    """Return the offending field path if a schema declares any credential/token-like field.

    Used as a guard test (§19): the manifest/result schemas must contain zero secret fields.

    The pattern targets *auth/credential* field names specifically (access/refresh/auth tokens,
    api keys, passwords, oauth, bearer, credential/secret). It deliberately does NOT flag the
    bare word "token": ``workspace_token`` is an opaque directory id, not a secret, and
    ``session_id`` is a non-secret UUID recorded per protocol §7.
    """
    pattern = re.compile(
        r"credential|secret|password|oauth|bearer"
        r"|api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token",
        re.IGNORECASE,
    )

    def walk(node: object, path: str) -> Optional[str]:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "properties" and isinstance(value, dict):
                    for field_name in value:
                        if pattern.search(field_name):
                            return f"{path}.properties.{field_name}"
                hit = walk(value, f"{path}.{key}")
                if hit:
                    return hit
        elif isinstance(node, list):
            for i, item in enumerate(node):
                hit = walk(item, f"{path}[{i}]")
                if hit:
                    return hit
        return None

    return walk(schema, "$")
