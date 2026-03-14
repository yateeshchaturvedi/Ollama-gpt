import argparse
import json
import logging
from pathlib import Path
from typing import Any

from rich import print

from app.clients.ollama import call_ollama
from app.config import settings
from app.logging_utils import setup_logging
from app.prompts import load_system_prompt
from app.protocol import parse_action, tool_schema_text
from app.tooling import build_tool_registry, execute_tool

TOOL_FUNCTIONS = build_tool_registry()


def format_conversation(messages: list[dict[str, str]]) -> str:
    """Create the prompt payload for `/api/generate` from conversation history."""
    lines = [load_system_prompt(), "", tool_schema_text(), ""]
    for msg in messages[-settings.max_history :]:
        role = msg["role"].upper()
        lines.append(f"{role}: {msg['content']}")
    lines.append("ASSISTANT:")
    return "\n".join(lines)


def run_turn(messages: list[dict[str, str]], model: str) -> str:
    """Run one user turn, allowing multiple tool calls before final output."""
    for step in range(settings.max_tool_steps):
        prompt = format_conversation(messages)
        try:
            if step == 0:
                print("[cyan]Thinking...[/cyan]")
            raw_response = call_ollama(prompt, model)
        except RuntimeError as exc:
            return f"Error contacting Ollama: {exc}"

        action = parse_action(raw_response, set(TOOL_FUNCTIONS.keys()))
        if action["type"] == "invalid_protocol":
            logging.warning("Invalid tool protocol output received; asking model to retry.")
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Your previous response violated the output protocol. "
                        "Return ONLY valid JSON in one of the supported shapes."
                    ),
                }
            )
            continue

        if action["type"] == "final":
            return action["content"]

        tool_name = action["tool"]
        args = action["args"]
        logging.info("Executing tool '%s' with args keys=%s", tool_name, list(args.keys()))
        tool_result = execute_tool(tool_name, args)

        messages.append({"role": "assistant", "content": json.dumps(action)})
        messages.append(
            {
                "role": "tool",
                "content": json.dumps({"tool": tool_name, "result": tool_result}, ensure_ascii=True),
            }
        )

    return (
        "I reached the tool-call step limit before producing a final response. "
        "Please refine your request or increase MAX_TOOL_STEPS."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local Ollama AI Agent")
    parser.add_argument(
        "--model",
        default=settings.ollama_model,
        help="Ollama model name (default from OLLAMA_MODEL).",
    )
    parser.add_argument("--prompt", help="Run a single prompt and exit.")
    parser.add_argument("--prompt-file", help="Read a single prompt from a text file and exit.")
    return parser.parse_args()


def main() -> None:
    setup_logging(settings.log_level)
    args = parse_args()
    model = args.model

    messages: list[dict[str, str]] = []
    print(f"[green]Local Ollama AI Agent Started (model={model})[/green]")

    one_shot_prompt = args.prompt
    if args.prompt_file:
        try:
            one_shot_prompt = Path(args.prompt_file).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"[red]Failed to read prompt file: {exc}[/red]")
            return

    if one_shot_prompt:
        messages.append({"role": "user", "content": one_shot_prompt})
        result = run_turn(messages, model)
        print(result)
        return

    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            break
        if not user_input:
            continue
        messages.append({"role": "user", "content": user_input})
        response = run_turn(messages, model)
        messages.append({"role": "assistant", "content": response})
        print("\nAI:")
        print(response)

