"""Treatment inputs: slot rendering, hashing, and provenance against the frozen manifest."""

import pytest
from _helpers import (TEST_APPROVAL, TEST_CLAUDE_MD, TEST_STATEMENT, TEST_WRAPPER,
                      make_treated_manifest, make_treatment)

from codeagent_configlab.hashing import sha256_bytes, sha256_text
from codeagent_configlab.treatment import (TASK_STATEMENT_SLOT, Treatment, expected_treatment_files,
                                           materialize_treatment, treatment_provenance_errors)


def test_statement_inserted_unmodified_exactly_once():
    t = make_treatment("C2")
    rendered = t.render_planning_prompt(TEST_STATEMENT)
    assert rendered.count(TEST_STATEMENT) == 1 and TASK_STATEMENT_SLOT not in rendered
    with pytest.raises(ValueError):
        Treatment(planning_wrapper="no slot").render_planning_prompt(TEST_STATEMENT)
    with pytest.raises(ValueError):
        Treatment(planning_wrapper=TASK_STATEMENT_SLOT * 2).render_planning_prompt(TEST_STATEMENT)


def test_hashes_and_same_bytes_for_c1_and_c2():
    c1, c2 = make_treatment("C1"), make_treatment("C2")
    assert c1.claude_md == c2.claude_md == TEST_CLAUDE_MD
    assert c1.claude_md_hash == c2.claude_md_hash == sha256_bytes(TEST_CLAUDE_MD)
    assert c2.planning_wrapper_hash == sha256_text(TEST_WRAPPER)
    assert c2.approval_message_hash == sha256_text(TEST_APPROVAL)


def test_from_files_roundtrip(tmp_path):
    (tmp_path / "md").write_bytes(TEST_CLAUDE_MD)
    (tmp_path / "w").write_text(TEST_WRAPPER, encoding="utf-8")
    (tmp_path / "a").write_text(TEST_APPROVAL, encoding="utf-8")
    t = Treatment.from_files(tmp_path / "md", tmp_path / "w", tmp_path / "a")
    assert t == make_treatment("C2")


def test_expected_state_comes_from_manifest():
    assert expected_treatment_files(make_treated_manifest("C0")) == {}
    m = make_treated_manifest("C1")
    assert expected_treatment_files(m) == {"CLAUDE.md": m.claude_md_hash}


@pytest.mark.parametrize("config", ["C0", "C1", "C2"])
def test_consistent_inputs_have_no_provenance_errors(config):
    assert treatment_provenance_errors(make_treated_manifest(config), make_treatment(config),
                                       TEST_STATEMENT) == []


def test_c2_missing_statement_or_texts_are_errors():
    m = make_treated_manifest("C2")
    assert treatment_provenance_errors(m, make_treatment("C2"), None)
    assert treatment_provenance_errors(m, Treatment(claude_md=TEST_CLAUDE_MD), TEST_STATEMENT)


def test_materialize_only_for_c1_c2_and_never_overwrites(tmp_path):
    materialize_treatment(tmp_path, "C0", make_treatment("C2"))
    assert not (tmp_path / "CLAUDE.md").exists()
    materialize_treatment(tmp_path, "C1", make_treatment("C1"))
    assert (tmp_path / "CLAUDE.md").read_bytes() == TEST_CLAUDE_MD
    with pytest.raises(FileExistsError):
        materialize_treatment(tmp_path, "C2", make_treatment("C2"))
