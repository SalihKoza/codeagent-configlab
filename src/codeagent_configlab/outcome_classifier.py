"""Per-invocation agent-outcome classification from structured CLI evidence (G4).

Claude Code 2.1.263 emits stream-json lines written by the CLI itself. Model and tool text only
ever appears *inside* string fields of those lines (``message.content``, ``tool_use_result``,
``result.result``); it cannot create a line or set a top-level field. Classification therefore
reads **only top-level structured fields**, never free text, and never stderr.

Evidence hierarchy (``docs/G4_OUTCOME_CLASSIFIER.md``):

1. the terminal ``result`` event: ``is_error``, ``api_error_status``, ``terminal_reason``;
2. the CLI's API-error wrapper (an assistant event with ``is_api_error_message: true`` and the
   ``error`` enum), ``system/api_retry`` (``error``, ``error_status``) and
   ``rate_limit_event.rate_limit_info.status``;
3. stderr is **not** used (mixed srt/bwrap/CLI diagnostics, provenance not guaranteed, no
   observed CLI auth format); it stays in ``stderr.txt`` for inspection;
4. the exit code decides only between ordinary ``completed`` and ``error_exit``.

Auth failure requires a terminal API error with status 401 or an auth ``error`` code. A
subscription-limit interruption requires a terminal API error with a limit ``error`` code **and** a
``rate_limit_event`` whose status is ``rejected``. That form has never been observed for real, so
the limit rule is provisional. Any other terminal API error stays ``error_exit`` with an
``api_error_unclassified`` reason: a false negative is inspectable, but a false infrastructure
invalidation driven by model-controlled text is not acceptable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .status import AgentOutcome

# CLI enum for the API-error wrapper's ``error`` field (read from the 2.1.263 binary).
AUTH_ERROR_CODES = frozenset({"authentication_failed", "oauth_org_not_allowed"})
LIMIT_ERROR_CODES = frozenset({"rate_limit", "billing_error"})
AUTH_STATUS = 401
LIMIT_REJECTED = "rejected"   # rate_limit_info.status: allowed | allowed_warning | rejected


@dataclass
class InvocationEvidence:
    """Structured observations from one invocation's event stream (never free text)."""

    result: Optional[dict] = None                   # subtype/is_error/api_error_status/terminal_reason
    api_errors: list = field(default_factory=list)  # [(error_code, status)] from API-error wrappers
    retries: list = field(default_factory=list)     # [(error_code, status)] from system/api_retry
    rate_limit_statuses: list = field(default_factory=list)
    last_api_state: Optional[tuple] = None          # ("retry"|"api_error"|"assistant", code, status)

    @classmethod
    def from_events(cls, events: list) -> "InvocationEvidence":
        ev = cls()
        for e in events:
            if not isinstance(e, dict):
                continue
            etype = e.get("type")
            if etype == "result":
                ev.result = {k: e.get(k) for k in ("subtype", "is_error", "api_error_status",
                                                   "terminal_reason")}
            elif etype == "assistant":
                if e.get("is_api_error_message") is True:
                    item = (_code(e.get("error")), _status(e.get("api_error_status")))
                    ev.api_errors.append(item)
                    ev.last_api_state = ("api_error", *item)
                else:
                    ev.last_api_state = ("assistant", None, None)
            elif etype == "system" and e.get("subtype") == "api_retry":
                item = (_code(e.get("error")), _status(e.get("error_status")))
                ev.retries.append(item)
                ev.last_api_state = ("retry", *item)
            elif etype == "rate_limit_event":
                info = e.get("rate_limit_info")
                if isinstance(info, dict) and isinstance(info.get("status"), str):
                    ev.rate_limit_statuses.append(info["status"])
        return ev

    @property
    def limit_rejected(self) -> bool:
        return LIMIT_REJECTED in self.rate_limit_statuses

    def terminal_api_error(self) -> Optional[tuple]:
        """(code, status) if the result reports that the invocation ended on an API error."""
        r = self.result
        if not r or r.get("is_error") is not True:
            return None
        status = _status(r.get("api_error_status"))
        if status is None and r.get("terminal_reason") != "api_error":
            return None
        code = self.api_errors[-1][0] if self.api_errors else None
        if status is None and self.api_errors:
            status = self.api_errors[-1][1]
        return code, status

    def to_dict(self) -> dict:
        return {"result": self.result, "api_errors": [list(x) for x in self.api_errors],
                "api_retries": [list(x) for x in self.retries],
                "rate_limit_statuses": sorted(set(self.rate_limit_statuses)),
                "last_api_state": list(self.last_api_state) if self.last_api_state else None}


@dataclass(frozen=True)
class Classification:
    outcome: AgentOutcome
    reason: str
    evidence: dict

    def to_dict(self) -> dict:
        return {"outcome": self.outcome.value, "reason": self.reason, "evidence": self.evidence}


def _code(v) -> Optional[str]:
    return v if isinstance(v, str) else None


def _status(v) -> Optional[int]:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _is_auth(code, status) -> bool:
    return status == AUTH_STATUS or code in AUTH_ERROR_CODES


def _is_limit(code, ev: InvocationEvidence) -> bool:
    return code in LIMIT_ERROR_CODES and ev.limit_rejected


def classify_invocation(exit_code: Optional[int], events: list, *, timed_out: bool = False,
                        termination_failed: bool = False, not_started: bool = False) -> Classification:
    """Classify one Claude CLI invocation. Reads structured fields only (see module docstring)."""
    ev = InvocationEvidence.from_events(events)
    evidence = ev.to_dict()

    def out(outcome, reason):
        return Classification(outcome, reason, evidence)

    # 1. G1: the harness lost control of the process tree -> harness failure, whatever else.
    if termination_failed:
        return out(AgentOutcome.HARNESS_ERROR, "harness:termination_failed")

    # 2. The CLI reports that the invocation ended on an API error.
    terminal = ev.terminal_api_error()
    if terminal is not None:
        code, status = terminal
        if _is_auth(code, status):
            src = f"result_api_error_status={status}" if status == AUTH_STATUS else f"error={code}"
            return out(AgentOutcome.AUTH_FAILURE, f"auth:{src}")
        if _is_limit(code, ev):
            return out(AgentOutcome.LIMIT_INTERRUPTED, f"limit:rate_limit_event_rejected+error={code}")
        return out(AgentOutcome.ERROR_EXIT, f"error_exit:api_error_unclassified:{code}/{status}")

    # 3. Cap reached. Infrastructure only if the cap was spent blocked on an auth/limit API error
    #    (the last API-level event is such an error, with no genuine assistant turn after it).
    if timed_out:
        if not_started:
            return out(AgentOutcome.TIMEOUT, "timeout:not_started_budget_exhausted")
        last = ev.last_api_state
        if last is not None and last[0] in ("retry", "api_error"):
            _, code, status = last
            if _is_auth(code, status):
                return out(AgentOutcome.AUTH_FAILURE, f"auth:timeout_blocked_on_{last[0]}:{code}/{status}")
            if _is_limit(code, ev):
                return out(AgentOutcome.LIMIT_INTERRUPTED,
                           f"limit:timeout_blocked_on_{last[0]}:{code}+rate_limit_event_rejected")
        return out(AgentOutcome.TIMEOUT, "timeout:cap_reached")

    # 4. Ordinary process outcome. Informational rate-limit events and recovered retries are
    #    recorded in the evidence but never change it.
    success = bool(ev.result) and ev.result.get("is_error") is False
    if exit_code == 0:
        return out(AgentOutcome.COMPLETED,
                   "completed:result_success" if success else "completed:exit_0_no_success_result")
    return out(AgentOutcome.ERROR_EXIT,
               "error_exit:nonzero_with_success_result" if success else "error_exit:nonzero")
