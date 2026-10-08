"""The harness loop: send a prompt, react to tool calls, repeat until the model
stops asking for tools.

The whole mechanism is Agent.run below. It is written to be read top to bottom.
"""

from typing import Any

import anthropic

from harness.session import NullLog, SessionLog
from harness.tools import Registry
from harness.trace import Tracer


class Agent:
    """Owns one conversation."""

    def __init__(self, client: anthropic.Anthropic, *, model: str, tools: Registry,
                 trace: Tracer, system: str = "", max_tokens: int = 16000,
                 log: SessionLog | NullLog | None = None):
        self.client = client
        self.model = model
        self.tools = tools
        self.trace = trace
        self.system = system
        self.max_tokens = max_tokens
        # Records every request and response; NullLog records nothing.
        self.log = log or NullLog()

        # The entire conversation state. The Messages API is stateless:
        # nothing is remembered server-side, so this list is resent in full on
        # every single request. Watch it grow in the trace.
        self.messages: list[dict[str, Any]] = []

    def run(self, prompt: str) -> str:
        """Sends prompt as a user turn and drives the loop to completion,
        returning the model's final text.

        Call it again on the same Agent to continue the conversation -- the
        history carries over, which is all "multi-turn chat" means.
        """
        self.messages.append({"role": "user", "content": prompt})
        final = ""

        # Nothing stops this loop but the model itself. What if it never stops
        # asking for tools?
        turn = 0
        while True:
            turn += 1

            # ── 1. Send the whole conversation, plus the tool definitions. ───
            #
            # The tools are re-declared every turn; the model has no memory of
            # them either. Definitions are name + description + JSON schema
            # only: the handler code never leaves this process.
            params: dict[str, Any] = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "messages": self.messages,
                "tools": self.tools.definitions(),
            }
            if self.system:
                params["system"] = self.system

            self.trace.request(turn, len(self.messages), self.model, self.tools.names())
            self.trace.json("request", params)
            self.log.request(params)

            try:
                response = self.client.messages.create(**params)
            except Exception as err:
                self.log.error(err)
                raise
            self.trace.json("response", response)
            self.log.response(response)

            # ── 2. Record the assistant turn BEFORE running any tool. ────────
            #
            # Every tool_result must be preceded by its tool_use block in the
            # history. Dropping the assistant message here -- or appending it
            # after the results -- makes the next request fail validation.
            self.messages.append({"role": "assistant", "content": response.content})

            # ── 3. Walk the content blocks. ──────────────────────────────────
            #
            # One assistant turn may mix prose with several tool calls, so this
            # is a loop over blocks, not a single check on the message.
            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if block.type == "text":
                    self.trace.text(block.text)
                    final = block.text
                elif block.type == "thinking":
                    self.trace.thinking(block.thinking)
                elif block.type == "tool_use":
                    # block.input is the model's arguments, already parsed
                    # from JSON by the SDK.
                    self.trace.tool_call(block.name, block.input)
                    result, is_error = self._run_tool(block.name, block.input)
                    self.trace.tool_result(block.name, result, is_error)

                    # block.id is the tool_use_id that pairs this result with
                    # the call above.
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id,
                                         "content": result, "is_error": is_error})

            self.trace.stop(response.stop_reason, response.usage.input_tokens,
                            response.usage.output_tokens)

            # ── 4. Done? ─────────────────────────────────────────────────────
            #
            # stop_reason is the loop's exit condition. Anything other than
            # tool_use means the model is finished talking to us.
            if response.stop_reason != "tool_use":
                return final
            if not tool_results:
                raise RuntimeError("model asked for tools but produced no tool_use blocks")

            # ── 5. Feed every result back as ONE user turn, then loop. ───────
            #
            # All results from this assistant turn go in a single message.
            # Splitting them across several user messages is valid, but teaches
            # the model to stop requesting tools in parallel.
            self.messages.append({"role": "user", "content": tool_results})

    def _run_tool(self, name: str, tool_input: dict[str, Any]) -> tuple[str, bool]:
        """Dispatches to the registry and turns an exception into text the
        model can read.

        It never raises: a failed tool is a normal event in the conversation,
        and the model routinely recovers from one. Aborting the loop on a tool
        error would be the wrong behaviour.
        """
        try:
            return self.tools.run(name, tool_input), False
        except Exception as err:
            return f"Error: {err}", True
