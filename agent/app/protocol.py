import json
import logging
from typing import Any


def tool_schema_text() -> str:
    """Return the tool-calling protocol prompt snippet."""
    return (
        "When an action is required, respond ONLY with valid JSON in one of these shapes:\n"
        '{"type":"tool_call","tool":"run_shell","args":{"command":"<command>"}}\n'
        '{"type":"tool_call","tool":"read_file","args":{"path":"<path>"}}\n'
        '{"type":"tool_call","tool":"write_file","args":{"path":"<path>","content":"<content>"}}\n'
        '{"type":"tool_call","tool":"github_actions_runs","args":{"repo":"owner/repo","per_page":5}}\n'
        '{"type":"tool_call","tool":"github_actions_run_logs","args":{"repo":"owner/repo","run_id":123}}\n'
        '{"type":"tool_call","tool":"github_pr_overview","args":{"repo":"owner/repo","pr_number":42}}\n'
        '{"type":"tool_call","tool":"github_pr_files","args":{"repo":"owner/repo","pr_number":42,"limit":20}}\n'
        '{"type":"tool_call","tool":"github_retry_workflow_run","args":{"repo":"owner/repo","run_id":123}}\n'
        '{"type":"tool_call","tool":"github_cancel_workflow_run","args":{"repo":"owner/repo","run_id":123}}\n'
        '{"type":"tool_call","tool":"github_required_checks_gate","args":{"repo":"owner/repo","pr_number":42}}\n'
        '{"type":"tool_call","tool":"github_deployment_status","args":{"repo":"owner/repo","per_page":10}}\n'
        '{"type":"tool_call","tool":"github_issue_triage","args":{"repo":"owner/repo","per_page":20}}\n'
        '{"type":"tool_call","tool":"github_security_summary","args":{"repo":"owner/repo","per_page":20}}\n'
        '{"type":"tool_call","tool":"github_changelog","args":{"repo":"owner/repo","base":"v1.0.0","head":"main"}}\n'
        '{"type":"tool_call","tool":"github_release_notes_to_pr_comment","args":{"repo":"owner/repo","pr_number":42,"base":"v1.0.0","head":"main"}}\n'
        '{"type":"tool_call","tool":"github_post_pr_comment","args":{"repo":"owner/repo","pr_number":42,"body":"review notes"}}\n'
        '{"type":"tool_call","tool":"github_pr_review_suggestions","args":{"repo":"owner/repo","pr_number":42,"limit":20}}\n'
        '{"type":"tool_call","tool":"github_multi_repo_dashboard","args":{"repos":["owner/repo","owner/repo2"]}}\n'
        '{"type":"tool_call","tool":"github_daily_digest","args":{"repos":["owner/repo","owner/repo2"]}}\n'
        '{"type":"final","content":"<your response to the user>"}\n'
        "Do not add markdown fences around JSON."
    )


def parse_action(raw_response: str, known_tools: set[str]) -> dict[str, Any]:
    """Parse model output into a tool_call or final message."""
    text = raw_response.strip()

    if text.startswith("```"):
        parts = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(parts).strip()

    decoder = json.JSONDecoder()
    try:
        parsed, index = decoder.raw_decode(text)
    except json.JSONDecodeError:
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
        logging.warning("Model returned trailing text after JSON payload. Ignoring trailing segment.")

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

