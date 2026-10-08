# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A minimal agent harness in Python, in the spirit of Claude Code, written for teaching purposes.
It makes two things visible:

1. How an initial prompt (system prompt + tool definitions + user message) is sent to the model.
2. How the harness reacts when the model asks for a tool: execute locally, feed the result
   back, loop.

Clarity beats features. The loop is one readable method that prints what crosses the wire.
If a change makes the mechanism harder to see in a live demo, it is the wrong change — that
includes adding abstraction layers, adding features listed under "Deliberately absent" below,
and quietly removing the trace output.

It is a port of the Go harness in `../agent-harness`, built up in four stages, one branch
each: `01-prompt`, `02-conversation`, `03-tools`, `04-harness` (= `main`). The history is
linear, so `git diff <stage> <next stage>` shows exactly one step. A change to an early
stage has to be carried through every later branch.

Python ≥ 3.12, managed with `uv`; the only runtime dependency is the `anthropic` SDK.

## Commands

```bash
uv run pytest                                       # all tests
uv run pytest tests/test_agent.py -k parallel       # single test

uv run harness "how many Python files are in this repo?"   # one-shot
uv run harness                                      # interactive
uv run harness -v "..."                             # full JSON of every request
uv run harness --ask "..."                          # approve each tool call
```

Authentication: the SDK reads `ANTHROPIC_API_KEY`, falling back to an `ant auth login`
profile. `anthropic.Anthropic()` takes no arguments and picks up either — never hardcode a
key or add an `--api-key` flag. Use the fake-API tests to verify changes; a live run spends
tokens.

## Architecture

| Module | Role |
|---|---|
| `harness.cli` | Flags, prompt input (args or REPL), the interactive approval hook |
| `harness.agent` | `Agent.run` — the loop and the conversation state. The file to read first. |
| `harness.tools` | `Registry` (name → definition + handler) and the built-ins: `read_file`, `list_dir`, `bash` |
| `harness.trace` | Prints requests, tool calls, results and token usage |
| `harness.session` | Session id and `session-log-<id>.md`, a record of every request and response |

The dependency direction is one-way: `cli` → `agent` → {`tools`, `trace`, `session`}. `tools`
knows nothing about the loop, which is what makes adding a tool a one-place change.

### The loop, and its invariants

`Agent.run` is numbered in comments 1–5. The invariants are load-bearing and each one is
covered by a test in `tests/test_agent.py` — if you change the loop, those tests are the
specification:

- **Conversation state is the `messages` list on `Agent`.** The API is stateless, so the
  harness resends the full history and re-declares every tool on every request. This is the
  single most important thing the demo shows; the trace prints the growing message count
  for exactly that reason.
- **Append `response.content` before executing tools, and append it whole.** A `tool_result`
  must be preceded in the history by its `tool_use` block, or the next request 400s. The
  content goes back unchanged, thinking blocks included — Claude Opus 5.5 always thinks, and
  its thinking blocks must be replayed as they came.
- **All tool results from one assistant turn go back in a single user message.** Splitting
  them across messages is valid but teaches the model to stop making parallel calls.
- **A failed tool returns a `tool_result` with `is_error: True`, and the loop continues.**
  `_run_tool` never raises. Letting the model see a failure and recover is part of the demo,
  so do not make a tool error fatal.
- **Tool input is already parsed** — `block.input` is a dict. Never string-match a
  serialized form.
- **`max_turns` bounds the loop** so a model that only ever calls tools still terminates.
- `approve` is the permission hook. A denial becomes an error result the model can read,
  not a silent no-op.

### Adding a tool

Add one `Tool` to `default_tools()` in `src/harness/tools.py`: name, description,
JSON-schema `properties`/`required`, and a `handler`. Nothing in `harness.agent` changes.
Route output through `truncate` — tool results re-enter the conversation every subsequent
turn, so an unbounded result is an unbounded bill.

## Testing

`tests/conftest.py` starts a local HTTP server that serves canned Messages responses; the
client points at it with `base_url`. The tests then assert on the *captured request bodies* —
history growth, message roles, `tool_use_id` pairing, `is_error` flags. This needs no API key
and spends no tokens; keep it that way. Add a canned response per expected turn — the fixture
fails the test if the harness makes more requests than there are responses.

## Claude API specifics

- Model: `claude-opus-5-5`. Never append a date suffix to a model ID.
- Thinking is always on with Claude Opus 5.5; `{"type": "disabled"}` and `budget_tokens`
  are rejected (400). Tune depth with `output_config.effort` if needed (default `medium`).
- Forced tool use (`tool_choice` `any`/`tool`) returns a 400 on this model; the harness uses
  the default `auto`.

## Deliberately absent

Streaming, prompt caching, context compaction, subagents, refusal fallbacks, and the SDK's
`client.beta.messages.tool_runner` — which drives this exact loop for you and is the right
answer in production. Hand-writing the loop is the entire point of this repository. Do not
"improve" the harness by adopting the tool runner; a pointer to it in a comment is the
correct treatment.
