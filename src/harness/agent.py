"""The conversation: send the history, record the answer, repeat on the next
prompt.

The whole mechanism is Agent.run below. It is written to be read top to bottom.
"""

from typing import Any

import anthropic

from harness.session import NullLog, SessionLog
from harness.trace import Tracer


class Agent:
    """Owns one conversation."""

    def __init__(self, client: anthropic.Anthropic, *, model: str, trace: Tracer,
                 system: str = "", max_tokens: int = 16000,
                 log: SessionLog | NullLog | None = None):
        self.client = client
        self.model = model
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
        """Sends prompt as a user turn and returns the model's answer.

        Call it again on the same Agent to continue the conversation -- the
        history carries over, which is all "multi-turn chat" means.
        """
        self.messages.append({"role": "user", "content": prompt})
        final = ""

        # ── 1. Send the whole conversation. ──────────────────────────────────
        #
        # The system prompt and every earlier turn travel with each request;
        # the model has no memory of them otherwise.
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": self.messages,
        }
        if self.system:
            params["system"] = self.system

        self.trace.request(1, len(self.messages), self.model)
        self.trace.json("request", params)
        self.log.request(params)

        try:
            response = self.client.messages.create(**params)
        except Exception as err:
            self.log.error(err)
            raise
        self.trace.json("response", response)
        self.log.response(response)

        # ── 2. Record the assistant turn. ────────────────────────────────────
        #
        # Without this line the next prompt would arrive without context: the
        # model would not know what it said a moment ago. The whole content
        # goes back, thinking blocks included, exactly as it arrived.
        self.messages.append({"role": "assistant", "content": response.content})

        # ── 3. Walk the content blocks. ──────────────────────────────────────
        #
        # An answer is a list of blocks, so this is a loop, not a single field.
        for block in response.content:
            if block.type == "text":
                self.trace.text(block.text)
                final = block.text
            elif block.type == "thinking":
                self.trace.thinking(block.thinking)

        self.trace.stop(response.stop_reason, response.usage.input_tokens,
                        response.usage.output_tokens)
        return final
