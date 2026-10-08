# agent-harness · stage 2: conversation

Stage 1 sent one prompt and forgot it. This stage keeps a conversation: every prompt is
sent together with the system prompt and the whole history so far.

| Branch | Adds |
|---|---|
| `01-prompt` | one request, print the answer |
| **`02-conversation`** | **REPL with history, system prompt and session log** |
| `03-tools` | tool definitions and the agent loop |
| `04-harness` / `main` | `bash`, approval hook, turn limit, full trace |

`git diff 01-prompt 02-conversation` shows exactly what this step adds.

## Running it

```bash
ant auth login                          # or: export ANTHROPIC_API_KEY=sk-ant-...

uv run harness "what is an agent harness?"
uv run harness                          # interactive; history carries across turns
uv run harness -v                       # dump the full JSON of every request
```

Flags: `--model`, `--max-tokens`, `--system`, `-v`.

## What to point at

- **The history grows 1 → 3 → 5.** The Messages API is stateless. The harness resends the
  entire conversation on every request; nothing is remembered on the server. Run with `-v`
  and watch the `messages` list get longer.
- **The system prompt travels with every request**, too.
- **Every request and response is written to `session-log-<id>.md`.** The id and the
  path are printed at startup. The log opens with the model and the system prompt, then
  records each request and response as JSON -- follow it with `tail -f session-log-*.md`.
- **More history means more input tokens.** The `in=` count rises with every turn, even for
  a short prompt -- this is where context cost comes from.

## Layout

| Path | What is there |
|---|---|
| `src/harness/cli.py` | Command line: flags, prompt input (args or REPL) |
| `src/harness/agent.py` | `Agent.run` and the conversation state |
| `src/harness/trace.py` | Printing what crosses the wire |
| `src/harness/session.py` | Session id and `session-log-<id>.md` with every request and response |

## Tests

```bash
uv run pytest
```

The tests run against a local fake of the Messages API serving canned responses and check
what the harness actually sent -- no API key, no token spend.
