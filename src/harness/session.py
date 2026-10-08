"""A session gives a conversation an identity and a written record.

Every request the harness sends and every response it receives is appended to
session-log-<id>.md, so a run can be read afterwards: the system prompt, the
history growing request by request, and every tool call.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


class SessionLog:
    """One session's record on disk."""

    def __init__(self, directory: str | Path, model: str, system: str):
        # A fresh id, and a log file opened with the model and the system
        # prompt, since neither shows up in the normal trace.
        self.id = str(uuid.uuid4())
        self.path = Path(directory) / f"session-log-{self.id}.md"
        self._file = self.path.open("w", encoding="utf-8")
        self._n = 0  # requests so far, numbered across the whole session
        self._write(f"# Session {self.id}\n\n"
                    f"- Started: {datetime.now().astimezone().isoformat(timespec='seconds')}\n"
                    f"- Model: {model}\n\n"
                    f"## System prompt\n\n```\n{system}\n```\n")

    def request(self, value: Any) -> None:
        """Records an outgoing request and starts the next number."""
        self._n += 1
        self._block(f"Request {self._n}", value)

    def response(self, value: Any) -> None:
        """Records the answer to the last request."""
        self._block(f"Response {self._n}", value)

    def error(self, err: BaseException) -> None:
        """Records that the last request failed."""
        self._write(f"\n## Error {self._n} · {_now()}\n\n```\n{err}\n```\n")

    def close(self) -> None:
        self._file.close()

    def _block(self, title: str, value: Any) -> None:
        dump = json.dumps(value, indent=2, ensure_ascii=False, default=_jsonable)
        self._write(f"\n## {title} · {_now()}\n\n```json\n{dump}\n```\n")

    def _write(self, s: str) -> None:
        # Flushed every time, so the log is complete up to the last request --
        # `tail -f` shows it live, and nothing is lost if the harness is killed.
        self._file.write(s)
        self._file.flush()


class NullLog:
    """Records nothing, so the harness runs the same with or without a log."""

    def request(self, value: Any) -> None: ...
    def response(self, value: Any) -> None: ...
    def error(self, err: BaseException) -> None: ...
    def close(self) -> None: ...


def _jsonable(value: Any) -> Any:
    return value.to_dict() if hasattr(value, "to_dict") else str(value)


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")
