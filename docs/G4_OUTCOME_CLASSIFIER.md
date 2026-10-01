# G4 — Evidence-based agent-outcome classification (2026-09-28)

Status: **RESOLVED.** Model-free. No Claude call was made.

## Root cause of the false positive

The old `runners.classify_outcome` worked as follows:
- It lower-cased `stderr` plus `json.dumps(every event)` and substring-matched `"401"`,
  `authentication_failed`, `oauth access token has expired`, … as auth.
- It then matched `quota`, `rate limit`, `resets at`, … as limit.

That text includes assistant text, tool input/output, uuids, ids and numbers. Replaying it
read-only over the preserved real Claude Code 2.1.263 streams in WSL reproduces the failure: a
real **successful** Candidate-2 run (`is_error=false`, `terminal_reason=completed`) is classified
`auth_failure` only because two event **`uuid`s contain the substring `401`**.

The successful G11 smoke was also recorded as `auth_failure`. Its stream was deleted by the smoke's
own cleanup, so the exact triggering field cannot be recovered. It has the same shape (a
successful stream with many uuids, ids and numbers, plus tool output from sandbox probes), and it
went through the same substring-over-everything scan.

## Why structured evidence is trustworthy

Every stream-json line is written by the CLI. Model and tool text appear only *inside* string
fields (`message.content`, `tool_use_result`, `result.result`). They cannot start a new line or
set a top-level field: a model that "prints" a JSON result line produces an escaped string inside
an assistant event. The classifier therefore reads only top-level fields that the CLI sets.

## Evidence hierarchy

1. **Terminal `result`**: `is_error`, `api_error_status`, `terminal_reason`. In the real
   expired-token run these were `is_error=true`, `api_error_status=401`,
   `terminal_reason=api_error`, and `subtype` was still `success`.
2. **Other structured API evidence:**
   - the **API-error wrapper**: an assistant event with top-level `is_api_error_message: true`
     and `error` from the CLI enum `authentication_failed | oauth_org_not_allowed |
     account_on_hold | billing_error | rate_limit | overloaded | invalid_request |
     model_not_found | server_error | unknown | max_output_tokens`;
   - **`system/api_retry`**: `error`, `error_status`;
   - **`rate_limit_event.rate_limit_info.status`**: `allowed | allowed_warning | rejected`.
3. **stderr is not used.** It mixes srt, bwrap and CLI diagnostics, its provenance is not
   guaranteed, and no CLI stderr auth format has been observed. It stays in `stderr.txt`.
4. **Exit code** decides only between ordinary `completed` and `error_exit`.

## Rules (`outcome_classifier.classify_invocation`)

| Order | Condition | Outcome, reason code |
|---|---|---|
| 1 | G1 termination failed | `harness_error`, `harness:termination_failed` |
| 2 | Terminal API error (`result.is_error` and a status or `terminal_reason=api_error`) with status 401 or code `authentication_failed`/`oauth_org_not_allowed` | `auth_failure`, `auth:…` |
| 2 | Terminal API error with code `rate_limit`/`billing_error` **and** a `rate_limit_event` `rejected` (**provisional**) | `limit_interrupted`, `limit:…` |
| 2 | Any other terminal API error | `error_exit`, `error_exit:api_error_unclassified:<code>/<status>` |
| 3 | Cap reached, and the last API-level event is an auth (or rejected-limit) retry/wrapper with no genuine assistant turn after it | `auth_failure` / `limit_interrupted`, `…:timeout_blocked_on_…` |
| 3 | Cap reached otherwise | `timeout` |
| 4 | Exit 0 | `completed`, `completed:result_success` |
| 4 | Exit ≠ 0 | `error_exit` |

Timeout precedence rationale: if the cap was spent while the CLI was still retrying a rejected
authentication (or a rejected subscription limit), the agent never worked, so the interruption is
infrastructure. Once a genuine assistant turn follows, the cap is an ordinary valid `timeout`.
Informational `rate_limit_event`s and recovered `api_retry`s never change the outcome.

## Recording

No schema change.
- `process.json` / `phaseN.process.json` gain `classification = {outcome, reason, evidence}`.
  `evidence` holds structured fields only, never text.
- `AgentRunOutcome.detail` carries the reason code. The lifecycle puts it into `invalid_reason`
  (auth) or `interruption_reason` (limit).
- C2 classifies each invocation separately (phase 1 / phase 2), as before.
- Since 2026-09-29, `process.json` / `phaseN.process.json` also gain `requested_model` and
  `observed_model` (see "Model provenance" below) — same no-schema-change reasoning: neither file
  is schema-validated.

## Model provenance (requested vs. observed) — 2026-09-29

A second, independent axis from G4's own outcome classification: whether the CLI's *observed*
model (the structured `model` field on its `type=="system"/subtype=="init"` stream-json event,
extracted by `session.observed_model_in_events` — never assistant/tool text, never stderr, exactly
mirroring `session_ids_in_events`) matches the *requested* model (`manifest.model_request`).
`outcome_classifier.classify_invocation` itself is **unchanged and stays model-unaware** — this
check lives one layer up, in `RunLifecycle.execute` (`lifecycle.py`), strictly *after* G4's own
outcome is known.

**Precedence** (evaluated only when `manifest.model_request` is frozen, i.e. not `OPEN`):

| Condition | Effect |
|---|---|
| `agent_outcome` is `auth_failure`, `limit_interrupted` or `harness_error` | provenance is **not checked** — G4's own classification already fully explains the run |
| `agent_outcome` is `completed`, `timeout`, or `error_exit`, and every phase's observed model equals the requested model | unaffected — `run_validity` stays whatever it already was |
| ... and some phase's observed model **differs** | `run_validity = invalid:harness`, `invalid_reason` names the requested value and every mismatched phase — checked identically for `completed`/`timeout`/`error_exit` (2026-09-29: a wrong model must not become invisible just because the run later errored ordinarily) |
| `agent_outcome` is `completed` or `timeout`, and some phase reported **no** observed model at all | `run_validity = invalid:harness`, `invalid_reason` names the phase(s) — a normally-progressing run with nothing captured is anomalous |
| `agent_outcome` is `error_exit`, and some phase reported **no** observed model at all (no init happened before the error) | provenance is **not checked** — there is no model-provenance evidence before init, so it is never invented into a verdict; the run keeps today's ordinary `error_exit` semantics |

A mismatch is an execution/provenance violation, never a task/acceptance failure — it reuses the
existing `invalid:harness` status this document's sibling (`PILOT_PLAN.md` §7) already committed
to for exactly this case. `invalid:harness` is already non-countable
(`status.derive_analysis_eligibility`) and already replacement-eligible
(`series.REPLACEMENT_ELIGIBLE_VALIDITY`) — no new status value and no new replacement policy.

C2's two phases are captured (and thus checked) independently: `phase1.process.json` and
`phase2.process.json` each carry their own `observed_model`, so a phase-2-only mismatch (e.g. a
mid-series model swap) is caught even when phase 1 matched.

## Fixtures and tests

- `fixtures/g4-classifier/` (README gives provenance): three sanitized **real** streams (uuid-401
  success, informational rate limit, expired OAuth), a **reconstructed** G11 success stream, and a
  **synthetic** limit stream.
- `tests/test_outcome_classifier.py` covers A–P, including:
  - a frozen copy of the old classifier, demonstrating the regression;
  - spoof tests (text in the assistant, tool output, final answer, stderr, and a JSON "result"
    line inside text);
  - timeout precedence;
  - C2 phase-1/phase-2 plumbing through `RunLifecycle` + `RealAgentRunner`;
  - `ModelProvenance` (2026-09-29): requested-vs-observed model, offline, through the real
    `RunLifecycle` + `RealAgentRunner` (synthetic init events plus the preserved
    `real_auth_expired` fixture for the auth-precedence case) — matching observed model stays
    valid; a differing or missing observed model fails closed as `invalid:harness`; auth failure
    and subscription-limit interruption before any model turn preserve their own semantics
    unaffected; a matched-model timeout stays `timeout`; spoof text never changes the observed
    model; identical behavior across C0/C1/C2 phase 1/phase 2; an unfrozen (`OPEN`) `model_request`
    never triggers the check; **added 2026-09-29:** `error_exit` with a matching init model stays
    ordinary `error_exit`, `error_exit` with a mismatched init model fails closed the same as
    `completed`/`timeout`, `error_exit` with no init event at all stays ordinary `error_exit`
    (missing is never invented for `error_exit`), and both a C2 phase-1-only and a
    phase-2-only `error_exit` mismatch fail closed independently.
- `tests/test_session.py` covers `observed_model_in_events` directly (structured field only,
  `None` when absent, immune to text/other-event spoofing).
- Read-only replay over all preserved real WSL streams: the expired-token run → `auth_failure`;
  all nine successful runs → `completed`.

## Limitations

- **Limit rule is provisional.** No real subscription-limit stream has been observed, so the
  required conjunction (a limit code plus `rejected`) may need adjusting when one is seen. Until
  then a real limit could surface as `error_exit:api_error_unclassified:…`. That is a false
  negative that stays inspectable.
- **Unknown terminal API errors** (overloaded, server errors, …) stay `error_exit` with an
  `api_error_unclassified` reason. Operator judgment follows PILOT_PLAN §10 ambiguous case 1.
- **CLI failure before any stream** (no events): `error_exit`. Raw stderr remains for inspection.
- **Residual spoof path.** A process that can write to the CLI's own stdout fd could inject whole
  lines. The model's Bash runs in the inner sandbox's PID namespace, where the CLI process is not
  visible.
