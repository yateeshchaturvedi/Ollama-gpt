"""Agent I/O protocol: schema generation and response parsing.

tool_schema_text() is now auto-generated from the TOOL_REGISTRY —
no more hand-maintained JSON example strings.

parse_action() remains responsible for parsing Ollama-style text
responses. In Phase 2 it will be replaced by native Gemini function
calling, but is retained here for the current Ollama backend.
"""
from __future__ import annotations

import json
import logging
from typing import Any


def tool_schema_text() -> str:
    """Auto-generate the tool-calling protocol prompt from the registry.

    Imported lazily to avoid a circular import at module load time.
    (tooling imports protocol indirectly through agent_runtime.)
    """
    # Lazy import to avoid circular dependency at startup
    from app.tooling import TOOL_REGISTRY, ToolDescriptor  # noqa: PLC0415

    lines: list[str] = [
        "When an action is required, respond ONLY with valid JSON in one of these shapes:",
    ]

    for descriptor in TOOL_REGISTRY.values():
        example = _build_example(descriptor)
        lines.append(json.dumps(example, separators=(",", ":")))

    lines.append('{"type":"final","content":"<your response to the user>"}')
    lines.append("Do not add markdown fences around JSON.")
    return "\n".join(lines)


def _build_example(descriptor: "ToolDescriptor") -> dict[str, Any]:
    """Build a compact JSON example for a tool call from its descriptor."""
    args: dict[str, Any] = {}

    for name in descriptor.required_str:
        args[name] = f"<{name}>"
    for name in descriptor.required_int:
        args[name] = 0
    for name in descriptor.required_str_any:
        args[name] = f"<{name}>"
    for name in descriptor.required_list_or_str:
        args[name] = ["owner/repo"]

    # Include optional args with their defaults as hints
    for name, default in descriptor.optional_args.items():
        args[name] = default

    if descriptor.needs_confirmation:
        args["confirmation"] = "CONFIRM"

    return {"type": "tool_call", "tool": descriptor.name, "args": args}


def parse_action(raw_response: str, known_tools: set[str]) -> dict[str, Any]:
    """Parse model output into a structured action dict.

    Returns one of:
      {"type": "tool_call", "tool": ..., "args": {...}}
      {"type": "final", "content": ...}
      {"type": "invalid_protocol", "content": ...}
    """
    text = raw_response.strip()

    # Strip markdown fences if the model wrapped JSON in them
    if text.startswith("```"):
        parts = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(parts).strip()

    decoder = json.JSONDecoder()
    try:
        parsed, index = decoder.raw_decode(text)
    except json.JSONDecodeError:
        # Heuristic: model returned a "simulated" tool transcript instead of JSON
        lowered = text.lower()
        suspicious_trace = (
            '"type"' in lowered
            and '"tool_call"' in lowered
            and ("tool:" in lowered or "assistant:" in lowered)
        )
        if suspicious_trace:
            return {
                "type": "invalid_protocol",
                "content": "Model returned simulated tool transcript instead of a valid JSON action.",
            }
        return {"type": "final", "content": raw_response}

    if not isinstance(parsed, dict):
        return {"type": "final", "content": raw_response}

    trailing = text[index:].strip()
    if trailing:
        logging.warning("Model returned trailing text after JSON payload; ignoring it.")

    msg_type = parsed.get("type")

    if msg_type == "tool_call":
        tool_name = parsed.get("tool")
        if tool_name not in known_tools:
            return {
                "type": "invalid_protocol",
                "content": f"Unsupported tool '{tool_name}'.",
            }
        if not isinstance(parsed.get("args"), dict):
            return {"type": "invalid_protocol", "content": "Invalid tool call args shape."}
        return parsed

    if msg_type == "final" and isinstance(parsed.get("content"), str):
        return parsed

    return {"type": "final", "content": raw_response}
