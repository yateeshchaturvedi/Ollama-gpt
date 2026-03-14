"""Backward-compatible entrypoint for the terminal agent."""

from app.agent_runtime import format_conversation, main, run_turn
from app.clients.ollama import call_ollama
from app.protocol import parse_action as _parse_action
from app.tooling import build_tool_registry, execute_tool
from app.tools import read_file

TOOL_FUNCTIONS = build_tool_registry()


def parse_action(raw_response: str):
    return _parse_action(raw_response, set(TOOL_FUNCTIONS.keys()))


if __name__ == "__main__":
    main()

