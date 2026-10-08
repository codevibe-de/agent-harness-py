# The life of a prompt

What actually happens, step by step, between typing a prompt and reading the answer.
Every step below maps to real code: `src/harness/cli.py` (setup), `src/harness/agent.py`
(the loop, whose comments are numbered 1–5 to match), `src/harness/tools.py` (execution),
`src/harness/trace.py` (the narration you see) and `src/harness/session.py` (the log).

The worked example throughout is:

```bash
uv run harness "how many Python files are in this repo?"
```

---

## Step 0 — Startup: build the pieces (`cli.py`)

Before anything is sent:

1. Flags are parsed (`--model`, `--max-turns`, `--max-tokens`, `--system`, `--ask`, `-v`).
2. `Tracer(sys.stdout, color=sys.stdout.isatty())` — colors only when attached to a terminal.
3. `default_tools()` builds the registry: `read_file`, `list_dir`, `bash`.
4. `SessionLog(".", model, system)` opens `session-log-<id>.md` with the model and the system prompt.
5. `Agent(anthropic.Anthropic(), ...)` creates an agent with an **empty** message list.
   Credentials come from `ANTHROPIC_API_KEY` or an `ant auth login` profile.
6. If there are prompt arguments, they become one prompt; otherwise the REPL reads prompts
   from stdin and the same `Agent` — so the same history — is reused for every turn.

Nothing has crossed the wire yet.

---

## Step 1 — The prompt becomes a user message

`Agent.run(prompt)` appends one message to the conversation:

```python
self.messages.append({"role": "user", "content": prompt})
```

History is now 1 message.

---

## Step 2 — Build and send the request

Every turn assembles the **entire** state from scratch, because the Messages API is stateless:

```python
params = {
    "model": self.model,
    "max_tokens": self.max_tokens,
    "messages": self.messages,            # the whole conversation, every time
    "tools": self.tools.definitions(),    # re-declared, every time
}
params["system"] = self.system
response = self.client.messages.create(**params)
```

Sample request body (turn 1, abbreviated — `-v` and the session log show the full thing):

```json
{
  "model": "claude-opus-5-5",
  "max_tokens": 16000,
  "system": "You are a small demonstration agent running inside a Python harness. ...",
  "messages": [
    {"role": "user", "content": "how many Python files are in this repo?"}
  ],
  "tools": [
    {
      "name": "read_file",
      "description": "Read the contents of a text file at the given path. Paths are relative to the working directory.",
      "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Path of the file to read"}},
        "required": ["path"]
      }
    },
    {"name": "list_dir", "description": "List the files and directories at the given path. ...", "input_schema": {"...": "..."}},
    {"name": "bash",     "description": "Run a shell command and return its combined stdout and stderr. ...", "input_schema": {"...": "..."}}
  ]
}
```

Note what the model receives about a tool: **name, description, JSON schema. That is all.**
The handler — the Python function that actually runs — never leaves this process.

The tracer prints the header line:

```
→ turn 1 request to claude-opus-5-5 · 1 message(s) in history · tools: read_file, list_dir, bash
```

---

## Step 3 — Record the assistant turn *before* running anything

```python
self.messages.append({"role": "assistant", "content": response.content})
```

This ordering is load-bearing: a `tool_result` must be preceded in the history by the
`tool_use` block it answers. Append the assistant message late (or not at all) and the
*next* request fails validation with a 400. The content goes back whole — Claude Opus 5.5
always thinks, and its thinking blocks have to be replayed exactly as they came.

Sample response (turn 1) — one assistant turn can mix prose with several tool calls:

```json
{
  "role": "assistant",
  "model": "claude-opus-5-5",
  "content": [
    {"type": "text", "text": "I'll look at the repository first."},
    {"type": "tool_use", "id": "toolu_01", "name": "list_dir", "input": {"path": "."}},
    {"type": "tool_use", "id": "toolu_02", "name": "bash", "input": {"command": "find . -name '*.py' -not -path './.venv/*' | wc -l"}}
  ],
  "stop_reason": "tool_use",
  "usage": {"input_tokens": 1204, "output_tokens": 88}
}
```

---

## Step 4 — Walk the content blocks

The loop checks `block.type`:

| Block | What the harness does |
|---|---|
| `text` | Print it; keep it as the candidate final answer |
| `thinking` | Print it dimmed as `[thinking]` when it has text (summaries are off by default) |
| `tool_use` | Take `block.input` — already parsed into a dict — and dispatch it |

Tool dispatch (`_run_tool`) is three things in order:

1. **Approval** — with `--ask`, the approval hook is consulted first. A denial
   short-circuits execution and returns the denial *text* as an error result, so the model
   learns why and can adapt instead of silently retrying.
2. **Registry lookup + execute** — `Registry.run(name, tool_input)` finds the handler by
   name. An unknown name is an error result, not a crash.
3. **Error conversion** — an exception becomes `"Error: ..."` text with `is_error=True`.
   `_run_tool` *never* raises: a failed tool is a normal conversational event, and aborting
   on one would be wrong.

All output is passed through `truncate` (8000-character cap), because tool results re-enter
the conversation on every subsequent turn — an unbounded result is an unbounded bill.

---

## Step 5 — Feed every result back as ONE user message

```python
self.messages.append({"role": "user", "content": tool_results})
```

Each result is paired to its call by `tool_use_id`:

```json
{
  "role": "user",
  "content": [
    {"type": "tool_result", "tool_use_id": "toolu_01", "content": "CLAUDE.md\nREADME.md\nsrc/\ntests/ ...", "is_error": false},
    {"type": "tool_result", "tool_use_id": "toolu_02", "content": "       9", "is_error": false}
  ]
}
```

Splitting these across two user messages would be valid — and would teach the model to stop
requesting tools in parallel. Hence the invariant: **one assistant turn's results ride in
one user message.**

History is now 3 messages. Loop back to Step 2.

---

## Step 6 — Exit conditions

The loop ends when one of these is true:

| Condition | Result |
|---|---|
| `stop_reason != "tool_use"` | Normal finish; return the last text block |
| `turn > max_turns` (default 20) | `RuntimeError: gave up after N turns` — bounds a model that only calls tools |
| `stop_reason == "tool_use"` but no `tool_use` blocks | `RuntimeError: model asked for tools but produced no tool_use blocks` |
| API error / Ctrl-C | The error is logged to the session log and reported; Ctrl-C exits quietly |

A tool failing is **not** on this list.

---

## Sequence view

```
user prompt
   │
   ▼
[1] append user message ──────────────────────────────┐
   │                                                  │
   ▼                                                  │
[2] messages.create(system, full history, all tools)  │
   │                                                  │
   ▼                                                  │
[3] append response.content  ← BEFORE any tool runs   │
   │                                                  │
   ▼                                                  │
[4] for each content block:                           │
       text      → print, remember as final           │
       thinking  → print                              │
       tool_use  → approve? → registry.run → truncate │
   │                                                  │
   ▼                                                  │
[6] stop_reason != tool_use ? ── yes → return final   │
   │ no                                               │
   ▼                                                  │
[5] append ONE user message with all tool_results ────┘
```

---

## Seeing it yourself

```bash
uv run harness -v "how many Python files are in this repo?"   # full JSON of every request
uv run harness --ask "delete the temp files"                   # approval hook in Step 4
tail -f session-log-*.md                                       # the session log, live
uv run pytest tests/test_agent.py -k feeds_result_back -v
```

The tests in `tests/test_agent.py` replay exactly this sequence against a local fake of the
Messages API, then assert on the captured request bodies — history growth, role ordering,
`tool_use_id` pairing and `is_error` flags. No API key, no token spend.
