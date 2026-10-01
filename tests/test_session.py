"""C2 session-continuity plumbing over stream-json events."""

from codeagent_configlab.session import (
    SessionSpec,
    verify_session_continuity,
    session_ids_in_events,
    observed_model_in_events,
    new_session_uuid,
)


def _events(sid):
    return [
        {"type": "system", "subtype": "init", "session_id": sid},
        {"type": "assistant", "message": {"content": []}},
        {"type": "result", "subtype": "success", "is_error": False, "session_id": sid},
    ]


def test_session_flag_mapping():
    assert SessionSpec("new", "u").cli_flag() == ("--session-id", "u")
    assert SessionSpec("resume", "u").cli_flag() == ("--resume", "u")


def test_continuity_verified_when_both_phases_use_same_uuid():
    u = new_session_uuid()
    assert verify_session_continuity(_events(u), _events(u), u)


def test_continuity_fails_on_mismatch():
    u = new_session_uuid()
    other = new_session_uuid()
    assert not verify_session_continuity(_events(u), _events(other), u)
    assert not verify_session_continuity(_events(other), _events(u), u)


def test_extra_foreign_session_id_breaks_continuity():
    u = new_session_uuid()
    tainted = _events(u) + [{"type": "result", "session_id": "foreign"}]
    assert not verify_session_continuity(tainted, _events(u), u)


def test_session_ids_extraction_ignores_non_session_events():
    u = new_session_uuid()
    assert session_ids_in_events(_events(u)) == {u}


def test_observed_model_extracted_from_init_event():
    events = [
        {"type": "system", "subtype": "init", "session_id": "u", "model": "claude-sonnet-5"},
        {"type": "assistant", "message": {"content": []}},
        {"type": "result", "subtype": "success", "is_error": False, "session_id": "u"},
    ]
    assert observed_model_in_events(events) == "claude-sonnet-5"


def test_observed_model_none_when_init_has_no_model_field():
    events = [
        {"type": "system", "subtype": "init", "session_id": "u"},
        {"type": "result", "subtype": "success", "is_error": False, "session_id": "u"},
    ]
    assert observed_model_in_events(events) is None
    assert observed_model_in_events([]) is None
    assert observed_model_in_events([{"garbage": True}, "not-a-dict"]) is None


def test_observed_model_ignores_non_init_events_and_text():
    # a "model" field on anything other than the system/init event must never be read -- including
    # a spoofed init-shaped event of the wrong subtype, and prose mentioning a model name.
    events = [
        {"type": "system", "subtype": "not_init", "model": "claude-opus-5"},
        {"type": "assistant", "message": {"role": "assistant", "model": "claude-opus-5",
                                          "content": [{"type": "text",
                                                       "text": "I am actually claude-opus-5"}]}},
        {"type": "result", "subtype": "success", "is_error": False, "session_id": "u",
         "result": "model: claude-opus-5"},
    ]
    assert observed_model_in_events(events) is None
