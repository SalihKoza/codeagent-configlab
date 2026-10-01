"""Status taxonomy — the separate axes of protocol §6.

The protocol deliberately keeps several *independent* axes rather than one composite score.
V0 defines **no** weighted or overall "quality" score, and this module must not introduce one.

Axes (protocol §6, with the task's requested concepts mapped onto the protocol's names):

* :class:`AgentOutcome`   — what the agent process did.
* :class:`RunValidity`    — whether the run was executed correctly (fixture, protocol, harness,
  hidden material, treatment integrity); it says nothing about countability.
* :class:`AnalysisEligibility` — whether the run counts as the planned observation for its
  cell (G3); derived from the other axes by :func:`derive_analysis_eligibility` only.
* :class:`Acceptance` / :class:`Regression` — evaluator verdicts (§6).
* :class:`Integrity`      — whether the agent stayed inside the tree/protected paths.
* :class:`C2Protocol`     — C2-only two-phase protocol conformance (§8).
* :class:`Preflight`      — pre-run environment gate (§4/§16); ``run not started`` on failure.

A legitimate task failure (``AgentOutcome.completed`` + acceptance ``fail``) is **valid**, not
invalid, and countable. Infrastructure/protocol problems (auth, harness bug, leak, carryover, …)
make a run invalid. A subscription-limit interruption is neither: it is an external execution
interruption -- ``run_validity`` stays ``valid`` and the run is ``not_countable:external_interruption``.
"""

from __future__ import annotations

from enum import Enum


class AgentOutcome(str, Enum):
    """What the agent process did (protocol §6 'Agent process' axis)."""

    COMPLETED = "completed"            # process exited on its own
    ERROR_EXIT = "error_exit"         # nonzero exit caused by the agent's own behavior
    TIMEOUT = "timeout"              # wall-clock cap expired; process tree terminated
    LIMIT_INTERRUPTED = "limit_interrupted"  # Pro subscription limit hit (§10, own class)
    AUTH_FAILURE = "auth_failure"    # auth/401 — infrastructure, not a task outcome
    HARNESS_ERROR = "harness_error"  # the harness itself failed


class RunValidity(str, Enum):
    """Whether the run was executed correctly (protocol §6/§10).

    ``VALID`` means fixture, protocol, harness, hidden-material protection and treatment
    integrity were all as specified. Everything else is an infrastructure/protocol invalidity with
    a recorded reason. Validity is **not** countability: a valid run interrupted by a
    subscription limit produced no observation (see :class:`AnalysisEligibility`, G3).
    Aliases in the task brief map here: invalid_fixture->INVALID_FIXTURE,
    invalid_hidden_material_exposure->INVALID_LEAK, invalid_harness_failure->INVALID_HARNESS,
    invalid_state_contamination->INVALID_CARRYOVER, infrastructure_auth_failure->
    INVALID_INFRASTRUCTURE (frozen, protocol §10). A subscription limit is NOT a validity value.
    """

    VALID = "valid"
    INVALID_INFRASTRUCTURE = "invalid:infrastructure"
    INVALID_HARNESS = "invalid:harness"
    INVALID_FIXTURE = "invalid:fixture"
    INVALID_LEAK = "invalid:leak"
    INVALID_CARRYOVER = "invalid:carryover"
    INVALID_C2_PROTOCOL = "invalid:c2_protocol"
    INVALID_TREATMENT_DRIFT = "invalid:treatment_drift"  # instruction state changed during the run
    PREFLIGHT_FAILED = "preflight_failed"  # run never started (§10)


# The subset of RunValidity values that mean "not executed as specified".
INVALID_VALUES = frozenset(v for v in RunValidity if v is not RunValidity.VALID)


class Acceptance(str, Enum):
    """Acceptance-test verdict (protocol §6)."""

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"      # evaluator could not run the acceptance tests
    NOT_RUN = "not_run"


class Regression(str, Enum):
    """Regression-test verdict (protocol §6)."""

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    NOT_RUN = "not_run"


class Integrity(str, Enum):
    """Whether the agent stayed within its tree and protected paths (protocol §6)."""

    CLEAN = "clean"
    PROTECTED_PATH_MODIFIED = "protected_path_modified"
    OUT_OF_TREE_WRITE_DETECTED = "out_of_tree_write_detected"


class C2Protocol(str, Enum):
    """C2 two-phase conformance (protocol §8); only meaningful for C2 runs."""

    OK = "ok"
    PHASE1_WRITE = "phase1_write"                    # working copy changed during phase 1
    PHASE_TRANSITION_FAILED = "phase_transition_failed"  # not same session / context lost
    NOT_APPLICABLE = "not_applicable"               # C0/C1 runs


class Preflight(str, Enum):
    """Result of a single preflight check (protocol §4/§16)."""

    OK = "ok"
    FAILED = "failed"       # a real contamination/environment problem -> run not started
    DEFERRED = "deferred"   # check not yet implemented; surfaced explicitly, never silent-pass


def is_valid(validity: RunValidity) -> bool:
    """True iff the run was executed as specified. Countability: :func:`derive_analysis_eligibility`."""
    return validity is RunValidity.VALID


def is_resolved(
    validity: RunValidity,
    acceptance: Acceptance,
    regression: Regression,
    integrity: Integrity,
) -> bool:
    """The V0 primary binary outcome (protocol §6): ``valid ∧ acceptance pass ∧ regression
    pass ∧ integrity clean``. This is NOT a score — it is a single derived boolean.
    """
    return (
        validity is RunValidity.VALID
        and acceptance is Acceptance.PASS
        and regression is Regression.PASS
        and integrity is Integrity.CLEAN
    )


# --- G3: analysis eligibility (countability) -------------------------------------------------

class AnalysisEligibility(str, Enum):
    """Whether a run counts as the planned observation for its task x configuration x repetition
    cell. Derived only by :func:`derive_analysis_eligibility`; never set by hand.

    ``not_countable`` never means "delete": every attempt is kept as immutable evidence, and a
    non-countable cell may later get a predeclared replacement attempt (G10, not here).
    """

    COUNTABLE = "countable"
    NOT_COUNTABLE_EXTERNAL_INTERRUPTION = "not_countable:external_interruption"
    NOT_COUNTABLE_INVALID = "not_countable:invalid"
    # G8: the agent attempt is fine but has no trustworthy evaluator verdict yet (evaluator
    # infrastructure error, or no verdict recorded). Protocol/PILOT_PLAN §10: validity unchanged,
    # verdict pending re-evaluation of the preserved final state -- never an agent rerun.
    NOT_COUNTABLE_EVALUATION_PENDING = "not_countable:evaluation_pending"


_NEVER_VALID_OUTCOMES = (AgentOutcome.AUTH_FAILURE, AgentOutcome.HARNESS_ERROR)


def derive_analysis_eligibility(run_validity, agent_outcome, *, acceptance, regression,
                                evaluator_error) -> tuple[AnalysisEligibility, str]:
    """The one canonical countability rule (G3, extended by G8). Accepts enums or stored strings.

    1. not ``valid`` -> ``not_countable:invalid`` (an invalidity outranks everything, incl. a limit);
    2. ``limit_interrupted`` -> ``not_countable:external_interruption`` (``subscription_limit``);
    3. ``auth_failure``/``harness_error`` recorded as ``valid`` is a contradiction -> never counted
       (``inconsistent:…``; :func:`check_status_consistency` rejects such records);
    4. evaluator infrastructure error (flag or an ``error`` verdict) ->
       ``not_countable:evaluation_pending`` (``evaluator_error``);
    5. no verdict on an axis (``not_run``) -> ``not_countable:evaluation_pending``
       (``no_evaluator_verdict``);
    6. ``completed``, ``error_exit``, ``timeout`` with real verdicts -> ``countable`` (legitimate
       outcomes incl. acceptance/regression ``fail``, §10).
    """
    validity, outcome = RunValidity(run_validity), AgentOutcome(agent_outcome)
    verdicts = (Acceptance(acceptance), Regression(regression))
    if validity is not RunValidity.VALID:
        reason = validity.value
        if outcome in (*_NEVER_VALID_OUTCOMES, AgentOutcome.LIMIT_INTERRUPTED):
            reason += f"/{outcome.value}"
        return AnalysisEligibility.NOT_COUNTABLE_INVALID, reason
    if outcome is AgentOutcome.LIMIT_INTERRUPTED:
        return AnalysisEligibility.NOT_COUNTABLE_EXTERNAL_INTERRUPTION, "subscription_limit"
    if outcome in _NEVER_VALID_OUTCOMES:
        return AnalysisEligibility.NOT_COUNTABLE_INVALID, f"inconsistent:valid/{outcome.value}"
    if evaluator_error or any(v.value == "error" for v in verdicts):
        return AnalysisEligibility.NOT_COUNTABLE_EVALUATION_PENDING, "evaluator_error"
    if any(v.value == "not_run" for v in verdicts):
        return AnalysisEligibility.NOT_COUNTABLE_EVALUATION_PENDING, "no_evaluator_verdict"
    return AnalysisEligibility.COUNTABLE, f"valid_outcome:{outcome.value}"


def analysis_eligibility_dict(run_validity, agent_outcome, *, acceptance, regression,
                              evaluator_error) -> dict:
    status, reason = derive_analysis_eligibility(run_validity, agent_outcome, acceptance=acceptance,
                                                 regression=regression, evaluator_error=evaluator_error)
    return {"status": status.value, "reason": reason}


def check_status_consistency(record: dict) -> list[str]:
    """The single cross-axis invariant for a result record (dict as in ``result.json``).

    Returns human-readable contradictions (empty = consistent). Used by ``RunResult.validate``.
    """
    errors: list[str] = []
    try:
        outcome = AgentOutcome(record["agent_outcome"])
        validity = RunValidity(record["run_validity"])
    except (KeyError, ValueError) as exc:
        return [f"status axes unreadable: {exc}"]
    limit = outcome is AgentOutcome.LIMIT_INTERRUPTED
    auth = outcome is AgentOutcome.AUTH_FAILURE
    if bool(record.get("limit_interrupted")) != limit:
        errors.append("limit_interrupted flag disagrees with agent_outcome")
    if bool(record.get("auth_failure")) != auth:
        errors.append("auth_failure flag disagrees with agent_outcome")
    if auth and validity is not RunValidity.INVALID_INFRASTRUCTURE:
        errors.append("auth_failure must be invalid:infrastructure (protocol §10)")
    if outcome is AgentOutcome.HARNESS_ERROR and validity is RunValidity.VALID:
        errors.append("harness_error cannot be a valid run")
    if limit and validity is RunValidity.INVALID_INFRASTRUCTURE:
        errors.append("a subscription limit is an external interruption, not invalid:infrastructure (G3)")
    if limit and (record.get("acceptance"), record.get("regression")) != ("not_run", "not_run"):
        errors.append("a limit-interrupted run has no evaluator verdict (acceptance/regression must be not_run)")
    try:
        acceptance, regression = Acceptance(record["acceptance"]), Regression(record["regression"])
    except (KeyError, ValueError) as exc:
        return errors + [f"verdict axes unreadable: {exc}"]
    evaluator_error = bool(record.get("evaluator_error"))
    axis_error = "error" in (acceptance.value, regression.value)
    if evaluator_error != axis_error:
        errors.append("evaluator_error must be true exactly when a verdict axis is 'error' (G8)")
    has_verdict = {acceptance.value, regression.value} & {"pass", "fail"}
    if has_verdict and not (record.get("artifacts") or {}).get("evaluator"):
        errors.append("a pass/fail verdict needs an auditable evaluator record (artifacts.evaluator)")
    derived = analysis_eligibility_dict(validity, outcome, acceptance=acceptance,
                                        regression=regression, evaluator_error=evaluator_error)
    if derived["reason"].startswith("inconsistent:"):
        errors.append(f"contradictory statuses: {derived['reason']}")
    stored = record.get("analysis_eligibility")
    if stored is not None and stored != derived:
        errors.append(f"analysis_eligibility {stored!r} != derived {derived!r}")
    return errors
