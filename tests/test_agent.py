import io

from conftest import message, text

from harness.agent import Agent
from harness.session import SessionLog
from harness.trace import Tracer


def new_agent(api, **kwargs) -> Agent:
    return Agent(api.client(), model="claude-opus-5-5", system="be brief",
                 trace=Tracer(io.StringIO()), **kwargs)


def test_run_keeps_history_across_calls(fake_api):
    """Calling run twice is what "multi-turn" means; nothing else is needed."""
    api = fake_api(message("end_turn", text("one")), message("end_turn", text("two")))
    agent = new_agent(api)

    agent.run("first")
    final = agent.run("second")

    assert final == "two"
    assert len(agent.messages) == 4  # user, assistant, user, assistant
    # The second request replays the earlier turns.
    assert len(api.requests[1]["messages"]) == 3


def test_system_prompt_travels_with_every_request(fake_api):
    """The system prompt is not stored either -- it is part of each request."""
    api = fake_api(message("end_turn", text("one")), message("end_turn", text("two")))
    agent = new_agent(api)

    agent.run("first")
    agent.run("second")

    assert [req["system"] for req in api.requests] == ["be brief", "be brief"]


def test_run_writes_session_log(fake_api, tmp_path):
    """Every request and response lands in the session log, numbered across the
    whole conversation."""
    api = fake_api(message("end_turn", text("one")), message("end_turn", text("two")))
    log = SessionLog(tmp_path, "claude-opus-5-5", "be brief")
    agent = new_agent(api, log=log)

    agent.run("first")
    agent.run("second")
    log.close()

    written = log.path.read_text()
    for want in ("## Request 1", "## Response 1", "## Request 2", "## Response 2", '"second"'):
        assert want in written
