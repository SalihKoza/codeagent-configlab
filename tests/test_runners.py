"""RealAgentRunner / RealCleanupRunner: argv, stdin, sanitized env, capture, classification."""

import json
import subprocess
from pathlib import Path

import pytest

from codeagent_configlab.process_control import (
    EXITED, TERMINATION_FAILED, TIMEOUT_TERMINATED, Deadline, ProcessRunResult,
)
from codeagent_configlab.envelope import AUTH_OVERRIDE_VARS, SecurityPolicy, implementation_envelope
from codeagent_configlab.outcome_classifier import classify_invocation
from codeagent_configlab.runners import RealAgentRunner, RealCleanupRunner
from codeagent_configlab.session import SessionSpec
from codeagent_configlab.status import AgentOutcome
from codeagent_configlab.workspace import make_working_copy


class FakeSpawn:
    """Records the call and returns a canned CompletedProcess (cleanup commands)."""

    def __init__(self, stdout=b"", stderr=b"", returncode=0):
        self.calls = []
        self._stdout, self._stderr, self._rc = stdout, stderr, returncode

    def __call__(self, argv, **kw):
        self.calls.append({"argv": argv, "kw": kw})
        return subprocess.CompletedProcess(argv, self._rc, stdout=self._stdout, stderr=self._stderr)


class FakeAgentSpawn(FakeSpawn):
    """Stands in for ``run_with_deadline``: returns a canned ProcessRunResult."""

    def __init__(self, stdout=b"", stderr=b"", returncode=0, termination=EXITED, timed_out=False,
                 **extra):
        super().__init__(stdout, stderr, returncode)
        self._termination, self._timed_out, self._extra = termination, timed_out, extra

    def __call__(self, argv, **kw):
        self.calls.append({"argv": argv, "kw": kw})
        return ProcessRunResult(termination=self._termination, timed_out=self._timed_out,
                                returncode=self._rc, stdout=self._stdout, stderr=self._stderr,
                                **self._extra)


def _wc(tmp_path):
    p = tmp_path / "pristine"
    p.mkdir()
    (p / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    return make_working_copy(p, tmp_path / "runs", seed_settings=True)


def _events_stdout(uuid):
    return ("\n".join(json.dumps(e) for e in [
        {"type": "system", "subtype": "init", "session_id": uuid, "model": "claude-haiku-4-5"},
        {"type": "result", "subtype": "success", "is_error": False, "session_id": uuid},
    ])).encode()


def test_argv_built_from_envelope_and_uses_stdin(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-be-removed")
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    uuid = "11111111-1111-1111-1111-111111111111"
    fake = FakeAgentSpawn(stdout=_events_stdout(uuid))
    runner = RealAgentRunner(
        home=str(tmp_path), harness_root=str(tmp_path / "hr"), model="haiku", effort="high",
        prompt="do the thing", tmp_root=str(tmp_path / "tmp"), spawn=fake,
        srt_path="/usr/bin/srt", claude_path="/usr/bin/claude",
    )
    wc = _wc(tmp_path)
    out = runner.run(wc, implementation_envelope("C0", SecurityPolicy()), SessionSpec("new", uuid))

    call = fake.calls[0]
    argv = call["argv"]
    assert argv[0] == "/usr/bin/srt" and "-s" in argv and "--" in argv
    assert "/usr/bin/claude" in argv
    assert "--session-id" in argv and uuid in argv
    assert "--settings" in argv and "--setting-sources" in argv
    assert "--effort" in argv and argv[argv.index("--effort") + 1] == "high"
    for bad in ("--continue", "--fork-session"):
        assert bad not in argv
    # task text delivered on stdin, never in argv
    assert call["kw"]["input"] == b"do the thing"
    assert not any("do the thing" in str(a) for a in argv)
    assert call["kw"]["cwd"] == str(wc.path)


def test_environment_is_sanitized(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    fake = FakeAgentSpawn(stdout=_events_stdout("u"))
    runner = RealAgentRunner(home=str(tmp_path), harness_root=str(tmp_path / "hr"), model="m", effort="high",
                             prompt="p", tmp_root=str(tmp_path / "tmp"), spawn=fake,
                             srt_path="/s", claude_path="/c")
    runner.run(_wc(tmp_path), implementation_envelope("C0"), SessionSpec("new", "u"))
    env = fake.calls[0]["kw"]["env"]
    for var in AUTH_OVERRIDE_VARS:
        assert var not in env
    assert env["DISABLE_AUTOUPDATER"] == "1"
    assert env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"
    assert "TMPDIR" in env


def test_result_capture_and_continuity(tmp_path):
    uuid = "22222222-2222-2222-2222-222222222222"
    fake = FakeAgentSpawn(stdout=_events_stdout(uuid), returncode=0)
    runner = RealAgentRunner(home=str(tmp_path), harness_root=str(tmp_path / "hr"), model="m", effort="high",
                             prompt="p", tmp_root=str(tmp_path / "tmp"), spawn=fake,
                             srt_path="/s", claude_path="/c")
    out = runner.run(_wc(tmp_path), implementation_envelope("C0"), SessionSpec("new", uuid))
    assert out.exit_code == 0
    assert out.agent_outcome is AgentOutcome.COMPLETED
    assert out.session_id == uuid
    assert out.session_continuity_verified is True
    assert len(out.events) == 2


def test_classify_invocation_structured_auth_limit_error():
    # G4: structured evidence only (full matrix: tests/test_outcome_classifier.py)
    auth = [{"type": "result", "subtype": "success", "is_error": True, "api_error_status": 401,
             "terminal_reason": "api_error"}]
    assert classify_invocation(1, auth).outcome is AgentOutcome.AUTH_FAILURE
    # a recovered 401 retry followed by a normal result is not an auth failure
    retry = [{"type": "system", "subtype": "api_retry", "error_status": 401},
             {"type": "result", "subtype": "success", "is_error": False}]
    assert classify_invocation(0, retry).outcome is AgentOutcome.COMPLETED
    # stderr/free text is not an input at all any more
    assert classify_invocation(1, []).outcome is AgentOutcome.ERROR_EXIT
    assert classify_invocation(0, []).outcome is AgentOutcome.COMPLETED
    assert classify_invocation(2, []).outcome is AgentOutcome.ERROR_EXIT


def test_cleanup_runner_runs_exact_targets_and_reports_failure():
    from codeagent_configlab.cleanup import build_cleanup_plan

    wc = "/home/cclab/cclab-harness-smoke/runs/ab12cd34ef567890"
    uuid = "33333333-3333-3333-3333-333333333333"
    plan = build_cleanup_plan(wc, [uuid], uid=1001)

    ok_spawn = FakeSpawn(returncode=0)
    report = RealCleanupRunner(spawn=ok_spawn).execute(plan)
    assert report["executed"] is True and report["cleanup_failed"] is False
    ran = [c["argv"] for c in report["commands"]]
    assert ["claude", "project", "purge", "-y", wc] in ran
    assert any(a[:3] == ["rm", "-rf", "--"] for a in ran)

    fail_spawn = FakeSpawn(returncode=1)
    rep2 = RealCleanupRunner(spawn=fail_spawn).execute(plan)
    assert rep2["executed"] is False and rep2["cleanup_failed"] is True


# --- G1: timeout vs harness-failure classification (no real process, no model) ---------------

def _runner(tmp_path, fake, **kw):
    return RealAgentRunner(home=str(tmp_path), harness_root=str(tmp_path / "hr"), model="m", effort="high",
                           prompt="p", tmp_root=str(tmp_path / "tmp"), spawn=fake,
                           srt_path="/s", claude_path="/c", **kw)


def test_timeout_is_agent_timeout_not_harness_error(tmp_path):
    uuid = "44444444-4444-4444-4444-444444444444"
    partial = _events_stdout(uuid).splitlines()[0]  # init emitted before the cap, no result event
    fake = FakeAgentSpawn(stdout=partial, returncode=None, termination=TIMEOUT_TERMINATED,
                          timed_out=True, signals_sent=["SIGTERM->group:123"],
                          deadline_budget_seconds=60.0)
    out = _runner(tmp_path, fake, timeout=60).run(
        _wc(tmp_path), implementation_envelope("C0"), SessionSpec("new", uuid))
    assert out.agent_outcome is AgentOutcome.TIMEOUT
    assert out.exit_code is None                      # never a fabricated exit code
    assert out.session_id == uuid                     # known before the cap -> kept
    assert len(out.events) == 1                       # pre-cap events preserved
    assert "cap" in out.detail and out.process["termination"] == TIMEOUT_TERMINATED
    # the runner turned `timeout` into a Deadline and handed it to the executor
    assert isinstance(fake.calls[0]["kw"]["deadline"], Deadline)


def test_termination_failure_is_harness_error(tmp_path):
    fake = FakeAgentSpawn(returncode=None, termination=TERMINATION_FAILED, timed_out=True,
                          survivors=[4242], error="survivors")
    out = _runner(tmp_path, fake, timeout=60).run(
        _wc(tmp_path), implementation_envelope("C0"), SessionSpec("new", "u"))
    assert out.agent_outcome is AgentOutcome.HARNESS_ERROR
    assert "4242" in out.detail


def test_timeout_with_auth_marker_keeps_infrastructure_precedence(tmp_path):
    ev = b'{"type": "system", "subtype": "api_retry", "error_status": 401}'
    fake = FakeAgentSpawn(stdout=ev, returncode=None, termination=TIMEOUT_TERMINATED, timed_out=True)
    out = _runner(tmp_path, fake, timeout=60).run(
        _wc(tmp_path), implementation_envelope("C0"), SessionSpec("new", "u"))
    assert out.agent_outcome is AgentOutcome.AUTH_FAILURE


def test_shared_deadline_takes_precedence_over_timeout(tmp_path):
    shared = Deadline.start(30)
    fake = FakeAgentSpawn(stdout=_events_stdout("u"))
    _runner(tmp_path, fake, timeout=999, deadline=shared).run(
        _wc(tmp_path), implementation_envelope("C0"), SessionSpec("new", "u"))
    assert fake.calls[0]["kw"]["deadline"] is shared


def test_no_timeout_means_no_deadline(tmp_path):
    fake = FakeAgentSpawn(stdout=_events_stdout("u"))
    _runner(tmp_path, fake).run(_wc(tmp_path), implementation_envelope("C0"), SessionSpec("new", "u"))
    assert fake.calls[0]["kw"]["deadline"] is None
