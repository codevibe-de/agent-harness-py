import io

from conftest import message, text

from harness.agent import Agent
from harness.session import SessionLog
from harness.tools import Registry, Tool
from harness.trace import Tracer


def new_agent(api, tools: Registry | None = None, **kwargs) -> Agent:
    return Agent(api.client(), model="claude-opus-5-5", system="be brief",
                 tools=tools or Registry(), trace=Tracer(io.StringIO()), **kwargs)


def tool_use(id: str, name: str, tool_input: dict | None = None) -> dict:
    return {"type": "tool_use", "id": id, "name": name, "input": tool_input or {}}


def echo(handler=lambda tool_input: "ok") -> Tool:
    return Tool(name="echo", description="Echo.", properties={}, handler=handler)


def test_run_executes_tool_and_feeds_result_back(fake_api):
    """The end-to-end shape of the harness: the model asks for a tool, the
    harness runs it locally and sends the result back, and the model's next
    turn ends the loop."""
    api = fake_api(message("tool_use", tool_use("toolu_1", "echo", {"text": "pong"})),
                   message("end_turn", text("The tool said pong.")))
    received = []
    agent = new_agent(api, Registry(echo(lambda tool_input: received.append(tool_input) or "pong")))

    final = agent.run("say pong")

    assert final == "The tool said pong."
    assert received == [{"text": "pong"}]
    assert len(api.requests) == 2

    # The conversation is resent in full every turn: user, assistant(tool_use),
    # user(tool_result). That growth is the whole point of the demo.
    first, second = (req["messages"] for req in api.requests)
    assert (len(first), len(second)) == (1, 3)

    # The assistant's tool_use must be replayed before its result, or the API
    # rejects the pairing.
    assert second[1]["role"] == "assistant"
    assert second[1]["content"][0]["type"] == "tool_use"

    # All results for a turn ride in ONE user message.
    results = second[2]["content"]
    assert len(results) == 1
    assert results[0]["type"] == "tool_result"
    assert results[0]["tool_use_id"] == "toolu_1"
    assert results[0]["is_error"] is False

    # The tools are re-declared every turn -- the model remembers nothing.
    assert len(api.requests[1]["tools"]) == 1


def test_parallel_tool_calls_return_in_one_message(fake_api):
    """Splitting results across user turns is valid, but it trains the model out
    of parallel tool use."""
    api = fake_api(message("tool_use", tool_use("toolu_1", "echo"), tool_use("toolu_2", "echo")),
                   message("end_turn", text("done")))

    new_agent(api, Registry(echo())).run("go")

    history = api.requests[1]["messages"]
    assert len(history) == 3
    assert [r["tool_use_id"] for r in history[2]["content"]] == ["toolu_1", "toolu_2"]


def test_tool_error_is_reported_not_fatal(fake_api):
    """A failing tool is a conversational event. The loop must keep going and
    let the model recover."""
    api = fake_api(message("tool_use", tool_use("toolu_1", "echo")),
                   message("end_turn", text("recovered")))

    def boom(tool_input):
        raise OSError("disk on fire")

    final = new_agent(api, Registry(echo(boom))).run("go")

    assert final == "recovered"
    result = api.requests[1]["messages"][2]["content"][0]
    assert result["is_error"] is True
    assert "disk on fire" in result["content"]


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
