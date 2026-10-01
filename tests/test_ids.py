"""Opaque id behavior: no experimental structure leaks through ids or workspace tokens.

Opaqueness here means the id is *not derived from* task/config/repetition, so an observer (the
agent, which can read its own working-directory path) cannot decode the cell. It does NOT mean a
random string never coincidentally contains a 2-char token like "c2"; a coincidence carries no
information. We therefore test the meaningful guarantees: the generators take no experimental
input at all, ids carry no separators (so they cannot be a descriptive ``a_b_c`` scheme), and a
deliberately descriptive name is correctly flagged by the opaqueness checker.
"""

import inspect

from codeagent_configlab.ids import (
    new_run_id,
    new_workspace_token,
    is_opaque,
    RUN_ID_PREFIX,
)


def test_run_ids_are_unique_and_prefixed():
    ids = {new_run_id() for _ in range(1000)}
    assert len(ids) == 1000
    assert all(i.startswith(RUN_ID_PREFIX) for i in ids)


def test_workspace_tokens_are_hex_and_unique():
    toks = {new_workspace_token() for _ in range(1000)}
    assert len(toks) == 1000
    assert all(all(c in "0123456789abcdef" for c in t) for t in toks)


def test_generators_take_no_experimental_input():
    # The strongest non-derivation guarantee: you cannot pass a task/config/rep in, so the id
    # cannot encode one.
    assert list(inspect.signature(new_run_id).parameters) == []
    assert list(inspect.signature(new_workspace_token).parameters) == []


def test_ids_have_no_separators_and_no_descriptive_tokens():
    # No '_' or '-' in the random body -> cannot be a descriptive "python_bugfix_c2_rep3" scheme.
    # Multi-char descriptive tokens are astronomically unlikely and checked here.
    descriptive = ("python_bugfix", "refactor", "feature", "p-smoke-001")
    for _ in range(300):
        rid = new_run_id()
        body = rid[len(RUN_ID_PREFIX):]
        assert "_" not in body and "-" not in body
        assert is_opaque(rid, forbidden_substrings=descriptive)
        tok = new_workspace_token()
        assert "_" not in tok and "-" not in tok
        assert is_opaque(tok, forbidden_substrings=descriptive)


def test_opaqueness_checker_flags_a_descriptive_name():
    # Sanity: the checker actually catches the naming scheme the protocol forbids (§9).
    assert not is_opaque("python_bugfix_C2_rep3", forbidden_substrings=("C2", "bugfix", "rep3"))


def test_run_id_and_workspace_token_differ():
    assert new_run_id() != new_workspace_token()
