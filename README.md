# agent-harness · stage 1: prompt

The smallest possible starting point: send one prompt to Claude, print the answer.
No conversation, no tools, no loop -- just the Messages API.

| Branch | Adds |
|---|---|
| **`01-prompt`** | **one request, print the answer** |
| `02-conversation` | REPL with history, system prompt and session log |
| `03-tools` | tool definitions and the agent loop |
| `04-harness` / `main` | `bash`, approval hook, turn limit, full trace |

`git diff 01-prompt 02-conversation` shows exactly what the next step adds.

## Running it

```bash
ant auth login                          # or: export ANTHROPIC_API_KEY=sk-ant-...

uv run harness "what is an agent harness?"
```

Flags: `--model`, `--max-tokens`.

## What to point at

- **A request is just data:** a model, `max_tokens` and a list of messages. The whole
  program is [`src/harness/cli.py`](src/harness/cli.py).
- **The answer is a list of content blocks**, not a string. This stage prints the text
  blocks and ignores the rest.
- **`stop_reason` and token usage** come back with every response. `end_turn` means the
  model finished; `max_tokens` means it was cut off.
