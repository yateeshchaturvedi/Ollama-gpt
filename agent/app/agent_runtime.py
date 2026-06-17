import argparse
import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator

from rich import print

from app.clients import get_llm_client
from app.config import settings
from app.logging_utils import setup_logging
from app.security import run_startup_checks
from app.tooling import build_tool_registry, execute_tool
from app.tools.tool_declarations import get_gemini_tools

TOOL_FUNCTIONS = build_tool_registry()


def run_turn(messages: list[dict[str, Any]], model: str) -> str:
    """Run one user turn, allowing multiple tool calls before final output."""
    client = get_llm_client()
    tools = get_gemini_tools() if settings.llm_provider == "gemini" else None

    for step in range(settings.max_tool_steps):
        try:
            if step == 0:
                print("[cyan]Thinking...[/cyan]")
            response = client.generate(messages, tools)
        except Exception as exc:
            return f"Error contacting LLM provider: {exc}"

        if isinstance(response, str):
            action = {"type": "final", "content": response}
        elif isinstance(response, dict):
            action = response
        else:
            action = {"type": "final", "content": str(response)}

        if action.get("type") == "invalid_protocol":
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

        if action.get("type") == "final":
            return action.get("content", "")

        tool_name = action.get("tool")
        args = action.get("args", {})
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


async def run_turn_stream(messages: list[dict[str, Any]], model: str) -> AsyncIterator[str]:
    """Async generator to stream the response of a turn (text only)."""
    client = get_llm_client()
    tools = get_gemini_tools() if settings.llm_provider == "gemini" else None

    for step in range(settings.max_tool_steps):
        try:
            response = client.generate(messages, tools)
        except Exception as exc:
            yield f"Error contacting LLM provider: {exc}"
            return

        if isinstance(response, str):
            action = {"type": "final", "content": response}
        elif isinstance(response, dict):
            action = response
        else:
            action = {"type": "final", "content": str(response)}

        if action.get("type") == "final":
            try:
                async for chunk in client.stream(messages, tools):
                    yield chunk
            except Exception:
                yield action.get("content", "")
            return

        if action.get("type") == "invalid_protocol":
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

        tool_name = action.get("tool")
        args = action.get("args", {})
        logging.info("Executing tool '%s' with args keys=%s", tool_name, list(args.keys()))
        tool_result = execute_tool(tool_name, args)

        messages.append({"role": "assistant", "content": json.dumps(action)})
        messages.append(
            {
                "role": "tool",
                "content": json.dumps({"tool": tool_name, "result": tool_result}, ensure_ascii=True),
            }
        )

    yield (
        "I reached the tool-call step limit before producing a final response. "
        "Please refine your request or increase MAX_TOOL_STEPS."
    )


async def analyze_failure_log(
    log: str,
    platform: str = "unknown",
    repo: str = "unknown",
    job: str = "unknown",
    trigger: str = "unknown",
    llm_config: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    """Stream a structured analysis of a CI/CD failure log."""
    llm_config = llm_config or {}
    client = get_llm_client(
        force_new=True,
        provider=llm_config.get("provider"),
        api_key=llm_config.get("api_key"),
        model_name=llm_config.get("model_name")
    )
    if hasattr(client, "analyze_failure_log"):
        async for chunk in client.analyze_failure_log(
            log=log, platform=platform, repo=repo, job=job, trigger=trigger
        ):
            yield chunk
    else:
        yield "AI failure analysis is only supported when LLM_PROVIDER is 'gemini'."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI DevOps Agent")
    default_model = settings.google_model if settings.llm_provider == "gemini" else settings.ollama_model
    parser.add_argument(
        "--model",
        default=default_model,
        help="Model name override (default depends on configured provider).",
    )
    parser.add_argument("--prompt", help="Run a single prompt and exit.")
    parser.add_argument("--prompt-file", help="Read a single prompt from a text file and exit.")
    return parser.parse_args()


def main() -> None:
    setup_logging(settings.log_level)
    run_startup_checks()
    args = parse_args()
    model = args.model

    messages: list[dict[str, Any]] = []
    print(f"[green]AI DevOps Agent Started (model={model})[/green]")

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

