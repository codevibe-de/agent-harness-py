# agent-harness · stage 3: tools

Stage 2 could only talk. This stage gives the model tools and turns the single request
into a loop: the model asks for a tool, the harness runs it locally, sends the result
back, and asks again -- until the model stops asking.

| Branch | Adds |
|---|---|
| `01-prompt` | one request, print the answer |
| `02-conversation` | REPL with history, system prompt and session log |
| **`03-tools`** | **tool definitions and the agent loop** |
| `04-harness` / `main` | `bash`, approval hook, turn limit, full trace |

`git diff -w 02-conversation 03-tools` shows exactly what this step adds (`-w` hides the
re-indentation from wrapping the request in a loop).

## Running it

```bash
ant auth login                          # or: export ANTHROPIC_API_KEY=sk-ant-...

uv run harness "how many Python files are in this repo?"
uv run harness                          # interactive; history carries across turns
uv run harness -v "..."                 # dump the full JSON of every request
```

Flags: `--model`, `--max-tokens`, `--system`, `-v`.

## What to point at

- **The model never runs anything.** It answers with a `tool_use` block -- a name and JSON
  input. The harness runs the Python handler and sends a `tool_result` back. The model only
  ever sees name, description and JSON schema of a tool.
- **The loop ends when `stop_reason` is no longer `tool_use`.** That is the model's way of
  saying "I am done".
- **Two tools in one turn.** The model can request several tools at once; the harness
  runs them and returns all results in a *single* user message.
- **A failed tool does not stop anything.** It goes back as `is_error: true` and the model
  works around it.
- **The session log shows the full exchange.** Every `tool_use` block and the `tool_result`
  that answers it are in `session-log-<id>.md`, request by request.
- **Nothing bounds the loop.** A model that keeps asking for tools would keep going --
  stage 4 adds a turn limit.

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
  │         │     tool_use  → dispatch to a local handler, collect a tool_result
  │         │
  │         └─ if response.stop_reason != "tool_use" → done
  │
  └──── append one user message with all tool_results and repeat
```

## Layout

| Path | What is there |
|---|---|
| `src/harness/cli.py` | Command line: flags, prompt input (args or REPL) |
| `src/harness/agent.py` | The loop and the conversation state -- the interesting file |
| `src/harness/tools.py` | Tool registry + `read_file`, `list_dir` |
| `src/harness/trace.py` | Printing what crosses the wire |
| `src/harness/session.py` | Session id and `session-log-<id>.md` with every request and response |

## Tests

```bash
uv run pytest
```

The loop is tested against a local fake of the Messages API serving canned responses, so
the full request/response cycle -- including parallel tool calls and tool errors -- runs
without an API key or a token spend.
