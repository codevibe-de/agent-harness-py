import re

from harness.session import NullLog, SessionLog


def test_log_records_requests_and_responses(tmp_path):
    log = SessionLog(tmp_path, "claude-opus-5-5", "be brief")
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", log.id)
    assert log.path == tmp_path / f"session-log-{log.id}.md"

    log.request({"prompt": "first"})
    log.response({"text": "one"})
    log.request({"prompt": "second"})
    log.error(RuntimeError("overloaded"))
    log.close()

    written = log.path.read_text()
    for want in (f"# Session {log.id}", "claude-opus-5-5", "## System prompt", "be brief",
                 "## Request 1", '"prompt": "first"', "## Response 1", '"text": "one"',
                 "## Request 2", "## Error 2", "overloaded"):
        assert want in written


def test_log_is_written_live(tmp_path):
    """Each entry is on disk as soon as it is recorded -- `tail -f` relies on it."""
    log = SessionLog(tmp_path, "claude-opus-5-5", "be brief")
    log.request({"prompt": "first"})
    assert "## Request 1" in log.path.read_text()
    log.close()


def test_null_log_records_nothing():
    """A harness without a session log must run unchanged."""
    log = NullLog()
    log.request("x")
    log.response("x")
    log.error(RuntimeError("x"))
    log.close()
