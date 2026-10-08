"""The harness's local tools, and the registry that exposes them to the model.

The registry is the only place that knows a tool exists. Adding a tool means
adding one Tool here -- the agent loop stays untouched.
"""

import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Caps what a tool may send back. Tool results re-enter the conversation on
# every later turn, so an unbounded result quietly becomes an unbounded bill.
MAX_TOOL_OUTPUT = 8000

# A handler receives the input the model produced, already parsed from JSON,
# and returns the text that goes back to the model. Raising is normal, not
# fatal: the agent loop turns it into an error result.
Handler = Callable[[dict[str, Any]], str]


@dataclass
class Tool:
    """One callable capability: the schema the model sees, plus the Python
    code that runs when the model asks for it."""

    name: str
    description: str
    properties: dict[str, Any]
    handler: Handler
    required: list[str] = field(default_factory=list)

    def definition(self) -> dict[str, Any]:
        # The half of the tool the model ever sees: a name, a description and
        # a JSON schema. The handler stays on this side of the wire.
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {"type": "object", "properties": self.properties,
                             "required": self.required},
        }


class Registry:
    """An ordered set of tools, keyed by name."""

    def __init__(self, *tools: Tool):
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            if tool.name in self._tools:
                raise ValueError(f"duplicate tool name {tool.name}")
            self._tools[tool.name] = tool

    def names(self) -> list[str]:
        return list(self._tools)

    def definitions(self) -> list[dict[str, Any]]:
        """The tools field of a Messages request."""
        return [tool.definition() for tool in self._tools.values()]

    def run(self, name: str, tool_input: dict[str, Any]) -> str:
        """Dispatches a tool call by name."""
        tool = self._tools.get(name)
        if tool is None:
            raise LookupError(f"no such tool {name!r} (available: {self.names()})")
        return tool.handler(tool_input)


def default_tools() -> Registry:
    """The tool set the harness starts with. Three tools are enough for the
    model to do real work while the whole surface still fits on a slide."""
    return Registry(read_file(), list_dir(), bash())


def read_file() -> Tool:
    def handler(tool_input: dict[str, Any]) -> str:
        return truncate(Path(tool_input["path"]).read_text())

    return Tool(
        name="read_file",
        description="Read the contents of a text file at the given path. Paths are relative to the working directory.",
        properties={"path": {"type": "string", "description": "Path of the file to read"}},
        required=["path"],
        handler=handler,
    )


def list_dir() -> Tool:
    def handler(tool_input: dict[str, Any]) -> str:
        directory = Path(tool_input.get("path") or ".")
        names = sorted(entry.name + ("/" if entry.is_dir() else "") for entry in directory.iterdir())
        return truncate("\n".join(names)) if names else "(empty directory)"

    return Tool(
        name="list_dir",
        description="List the files and directories at the given path. Defaults to the working directory.",
        properties={"path": {"type": "string", "description": 'Directory to list; defaults to "."'}},
        handler=handler,
    )


def bash() -> Tool:
    """Runs a shell command.

    This is deliberately unsandboxed -- it is what makes the demo feel like a
    real harness. A production harness would gate it behind user approval; see
    the approval hook in harness.agent.
    """
    def handler(tool_input: dict[str, Any]) -> str:
        command = tool_input.get("command", "")
        if not command.strip():
            raise ValueError("empty command")
        proc = subprocess.run(["bash", "-c", command], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)
        output = truncate(proc.stdout)
        if proc.returncode != 0:
            # A non-zero exit is information for the model, not a harness
            # failure -- hand back the output alongside the status.
            raise RuntimeError(f"exit status {proc.returncode}\n{output}".rstrip())
        return output or "(no output)"

    return Tool(
        name="bash",
        description="Run a shell command and return its combined stdout and stderr. Use for anything the other tools do not cover.",
        properties={"command": {"type": "string", "description": "The shell command to run"}},
        required=["command"],
        handler=handler,
    )


def truncate(s: str) -> str:
    if len(s) <= MAX_TOOL_OUTPUT:
        return s
    return s[:MAX_TOOL_OUTPUT] + f"\n... [truncated, {len(s)} characters total]"
