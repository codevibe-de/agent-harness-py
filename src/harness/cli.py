"""Stage 2: a conversation with Claude. Every prompt is sent together with the
whole history so far.

    uv run harness "what is an agent harness?"
    uv run harness -v                 # interactive, full JSON trace

Authentication comes from ANTHROPIC_API_KEY, or from an `ant auth login`
profile -- the zero-argument client picks up either.
"""

import argparse
import sys

import anthropic

from harness.agent import Agent
from harness.session import SessionLog
from harness.trace import Tracer

DEFAULT_SYSTEM = """You are a small demonstration agent running inside a Python harness.
Answer in one short paragraph."""


def main() -> None:
    parser = argparse.ArgumentParser(prog="harness")
    parser.add_argument("prompt", nargs="*", help="one-shot prompt; without it, prompts are read interactively")
    parser.add_argument("--model", default="claude-opus-5-5", help="model id")
    parser.add_argument("-v", "--verbose", action="store_true", help="dump the full JSON of every request and response")
    parser.add_argument("--max-tokens", type=int, default=16000, help="max_tokens per request")
    parser.add_argument("--system", default=DEFAULT_SYSTEM, help="system prompt")
    args = parser.parse_args()

    try:
        run(args)
    except KeyboardInterrupt:
        print()  # Ctrl-C ends the run quietly
    except Exception as err:
        print(f"\nharness: {err}", file=sys.stderr)
        sys.exit(1)


def run(args: argparse.Namespace) -> None:
    trace = Tracer(sys.stdout, color=sys.stdout.isatty(), verbose=args.verbose)

    # One session per run: an id and a log file with every request and
    # response, the system prompt included.
    log = SessionLog(".", args.model, args.system)
    try:
        agent = Agent(anthropic.Anthropic(), model=args.model, trace=trace,
                      system=args.system, max_tokens=args.max_tokens, log=log)

        trace.info(f"harness ready · model={args.model}")
        trace.info(f"session {log.id} · log: {log.path}")

        # One-shot: everything after the flags is the prompt.
        if args.prompt:
            agent.run(" ".join(args.prompt))
            return

        # Otherwise read prompts from stdin. The Agent keeps its history
        # between calls, so this is a conversation, not a series of one-shots.
        while True:
            try:
                prompt = input("\n> ").strip()
            except EOFError:
                print()
                return
            if not prompt:
                continue
            if prompt in ("exit", "quit"):
                return
            try:
                agent.run(prompt)
            except Exception as err:
                print(f"harness: {err}", file=sys.stderr)
    finally:
        log.close()
