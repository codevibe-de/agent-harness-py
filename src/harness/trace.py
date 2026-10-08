"""Prints what crosses the wire.

The harness exists to be watched, so the trace is a feature, not debug output:
every request and every token count is shown.
"""

import json
from typing import Any, TextIO

COLOR = {"dim": "\033[2m", "bold": "\033[1m", "blue": "\033[34m", "green": "\033[32m",
         "yellow": "\033[33m", "red": "\033[31m", "reset": "\033[0m"}
PLAIN = {name: "" for name in COLOR}


class Tracer:
    """Writes the harness's narration. Verbose adds the full JSON of each
    request and response."""

    def __init__(self, out: TextIO, color: bool = False, verbose: bool = False):
        self.out = out
        self.c = COLOR if color else PLAIN
        self.verbose = verbose

    def request(self, turn: int, messages: int, model: str) -> None:
        """Announces an outgoing request. `messages` is the size of the history --
        watching it grow is the point: the API is stateless, so the harness resends
        everything every turn."""
        c = self.c
        self._print(f"{c['bold']}{c['blue']}→ turn {turn}{c['reset']} "
                    f"{c['dim']}request to {model} · {messages} message(s) in history{c['reset']}")

    def text(self, s: str) -> None:
        """Reports assistant prose."""
        if s.strip():
            self._print(f"\n{s.strip()}\n")

    def thinking(self, s: str) -> None:
        """Reports a summarized reasoning block, when one is present."""
        if s.strip():
            self._print(f"{self.c['dim']}[thinking] {_indent(s.strip(), ' ' * 11)}{self.c['reset']}")

    def stop(self, reason: str, tokens_in: int, tokens_out: int) -> None:
        """Reports the stop reason and token usage that ended a turn."""
        self._print(f"{self.c['dim']}  stop_reason={reason} · in={tokens_in} out={tokens_out} tokens{self.c['reset']}")

    def info(self, message: str) -> None:
        """Prints a one-line harness note."""
        self._print(f"{self.c['dim']}{message}{self.c['reset']}")

    def json(self, label: str, value: Any) -> None:
        """Dumps a full payload; only in verbose mode."""
        if self.verbose:
            dump = json.dumps(value, indent=2, ensure_ascii=False, default=_jsonable)
            self._print(f"{self.c['dim']}--- {label} ---\n{dump}{self.c['reset']}")

    def _print(self, s: str) -> None:
        print(s, file=self.out, flush=True)


def _jsonable(value: Any) -> Any:
    # SDK objects (the response, content blocks in the history) know how to
    # turn themselves into plain dicts.
    return value.to_dict() if hasattr(value, "to_dict") else str(value)


def _indent(s: str, prefix: str) -> str:
    return s.replace("\n", "\n" + prefix)
