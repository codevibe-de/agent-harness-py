"""Stage 1: send one prompt to Claude and print the answer.

    uv run harness "what is an agent harness?"

Authentication comes from ANTHROPIC_API_KEY, or from an `ant auth login`
profile -- the zero-argument client picks up either.
"""

import argparse
import sys

import anthropic


def main() -> None:
    parser = argparse.ArgumentParser(prog="harness")
    parser.add_argument("prompt", nargs="+", help="the prompt to send")
    parser.add_argument("--model", default="claude-opus-5-5", help="model id")
    parser.add_argument("--max-tokens", type=int, default=16000, help="max_tokens per request")
    args = parser.parse_args()

    try:
        run(args.model, args.max_tokens, " ".join(args.prompt))
    except anthropic.APIError as err:
        print(f"\nharness: {err}", file=sys.stderr)
        sys.exit(1)


def run(model: str, max_tokens: int, prompt: str) -> None:
    client = anthropic.Anthropic()

    # One request: a model, a token limit and a single user message. That is
    # the whole contract with the Messages API.
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    # The answer is a list of content blocks, not a string. For now we only
    # care about the text ones.
    for block in response.content:
        if block.type == "text":
            print(block.text)

    print(f"\nstop_reason={response.stop_reason} · "
          f"in={response.usage.input_tokens} out={response.usage.output_tokens} tokens")
