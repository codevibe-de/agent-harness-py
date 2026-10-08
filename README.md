# agent-harness

A minimal agent harness in Python, in the spirit of Claude Code. It exists to make two
things visible:

1. how an initial prompt — system prompt, tool definitions, user message — is sent to the model, and
2. how the harness reacts when the model asks for a tool: run it locally, feed the result back, loop.

Everything else was left out on purpose. The loop is `Agent.run` in
[`src/harness/agent.py`](src/harness/agent.py), and it is the thing to read.

The harness is built up in four stages, one branch each; this is the last one.

| Branch | Adds |
|---|---|
| `01-prompt` | one request, print the answer |
| `02-conversation` | REPL with history, system prompt and session log |
| `03-tools` | tool definitions and the agent loop |
| **`04-harness` / `main`** | **`bash`, approval hook, turn limit, full trace** |

`git diff 03-tools 04-harness` shows exactly what this step adds.

## Running it

```bash
ant auth login                          # or: export ANTHROPIC_API_KEY=sk-ant-...

uv run harness "how many Python files are in this repo?"
uv run harness                          # interactive; history carries across turns
uv run harness --ask "delete the temp files"   # approve each tool call
uv run harness -v "..."                 # dump the full JSON of every request
```

Flags: `--model`, `--max-tokens`, `--max-turns`, `--system`, `--ask`, `-v`.

Every run writes `session-log-<id>.md` to the current directory: the system prompt, then
every request and response as JSON. `tail -f session-log-*.md` follows it live.

## What to point at

- **The history grows 1 → 3 → 5.** The Messages API is stateless. The harness resends the
  entire conversation, and re-declares every tool, on every single request. Nothing is
  remembered on the server.
- **Two tools in one turn.** The model can request several tools at once; the harness runs
  them and returns all results in a *single* user message.
- **A failed tool does not stop anything.** A tool error is a normal conversational
  event — it goes back as `is_error: true` and the model works around it.
- **A denied tool does not stop anything either.** With `--ask`, a "no" goes back to the
  model as an error result, and the model asks what to do instead.

## The loop

```
build tools + system prompt
        │
        ▼
  ┌──> messages.create(model, messages, tools)
  │         │
  │         ├─ append response.content to messages   ← always, before handling tool calls
  │         │
  │         ├─ walk response.content:
  │         │     text      → print to user
  │         │     tool_use  → approve? → dispatch to a local handler, collect a tool_result
  │         │
  │         └─ if response.stop_reason != "tool_use" → done
  │
  └──── append one user message with all tool_results and repeat
```

## Layout

| Path | What is there |
|---|---|
| `src/harness/cli.py` | Command line: flags, prompt input, the approval hook |
| `src/harness/agent.py` | The loop and the conversation state — the interesting file |
| `src/harness/tools.py` | Tool registry + `read_file`, `list_dir`, `bash` |
| `src/harness/trace.py` | Printing what crosses the wire |
| `src/harness/session.py` | Session id and `session-log-<id>.md` with every request and response |

## Adding a tool

Add one `Tool` to `default_tools()`. The agent loop does not change.

```python
def word_count() -> Tool:
    def handler(tool_input):
        return str(len(Path(tool_input["path"]).read_text().split()))

    return Tool(
        name="word_count",
        description="Count the words in a file.",
        properties={"path": {"type": "string", "description": "File to count"}},
        required=["path"],
        handler=handler,
    )
```

The model only ever sees the name, description and schema. The handler never leaves the process.

## Tests

```bash
uv run pytest
```

The loop is tested against a local fake of the Messages API serving canned responses, so
the full request/response cycle — including parallel tool calls, tool errors, denials and
the turn cap — runs without an API key or a token spend.

## Not included, on purpose

Streaming, prompt caching, context compaction, subagents, and the SDK's own tool runner
(`client.beta.messages.tool_runner`, which drives this exact loop for you in production).
Writing the loop by hand is the point here.
