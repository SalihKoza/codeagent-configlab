# evaluator-security fixture (G5s) — NOT a pilot or final task

Model-free fixture for the evaluator sandbox. `candidate/` is copied over `pristine/` to form
an "agent" final state whose code probes the evaluator sandbox with harmless actions:
- reads, writes and listings of canary locations;
- a TCP connect to a local listener;
- child processes.

The probes print a JSON matrix of outcomes (booleans and hashes only, never file contents).
Canary paths are passed in `targets.json`, which the test writes. No real secret is ever used.
`tests/test_evaluator_sandbox.py` and `spike/g5s-evaluator-sandbox/g5s_probe.py` drive it.
