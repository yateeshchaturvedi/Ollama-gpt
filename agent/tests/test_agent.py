import json

from app import agent_runtime
from app.clients import ollama as ollama_client
from app.protocol import parse_action
from app.tooling import execute_tool


def test_parse_action_tool_call() -> None:
    raw = json.dumps(
        {"type": "tool_call", "tool": "read_file", "args": {"path": "README.md"}}
    )
    parsed = parse_action(raw, set(agent_runtime.TOOL_FUNCTIONS.keys()))
    assert parsed["type"] == "tool_call"
    assert parsed["tool"] == "read_file"


def test_parse_action_non_json_falls_back_to_final() -> None:
    parsed = parse_action("normal text response", set(agent_runtime.TOOL_FUNCTIONS.keys()))
    assert parsed["type"] == "final"
    assert parsed["content"] == "normal text response"


def test_parse_action_executes_leading_tool_call_in_mixed_output() -> None:
    mixed = (
        '{"type":"tool_call","tool":"read_file","args":{"path":"/etc/demo.txt"}}\n'
        'TOOL: {"tool":"read_file","result":"x"}\nASSISTANT: done'
    )
    parsed = parse_action(mixed, set(agent_runtime.TOOL_FUNCTIONS.keys()))
    assert parsed["type"] == "tool_call"
    assert parsed["tool"] == "read_file"


def test_parse_action_detects_invalid_protocol_when_no_parsable_json() -> None:
    mixed = (
        'prefix text {"type":"tool_call","tool":"read_file","args":{"path":"/etc/demo.txt"}}\n'
        'TOOL: {"tool":"read_file","result":"x"}\nASSISTANT: done'
    )
    parsed = parse_action(mixed, set(agent_runtime.TOOL_FUNCTIONS.keys()))
    assert parsed["type"] == "invalid_protocol"


def test_parse_action_accepts_json_with_trailing_text() -> None:
    payload = (
        '{"type":"tool_call","tool":"read_file","args":{"path":"README.md"}}\n'
        "extra text ignored"
    )
    parsed = parse_action(payload, set(agent_runtime.TOOL_FUNCTIONS.keys()))
    assert parsed["type"] == "tool_call"
    assert parsed["tool"] == "read_file"


def test_parse_action_rejects_unknown_tool_call() -> None:
    raw = '{"type":"tool_call","tool":"integrate_with_azure","args":{}}'
    parsed = parse_action(raw, set(agent_runtime.TOOL_FUNCTIONS.keys()))
    assert parsed["type"] == "invalid_protocol"


def test_parse_action_accepts_github_tool_call() -> None:
    raw = (
        '{"type":"tool_call","tool":"github_pr_overview",'
        '"args":{"repo":"owner/repo","pr_number":12}}'
    )
    parsed = parse_action(raw, set(agent_runtime.TOOL_FUNCTIONS.keys()))
    assert parsed["type"] == "tool_call"
    assert parsed["tool"] == "github_pr_overview"


def test_execute_tool_invalid_args() -> None:
    result = execute_tool("read_file", {"path": ""})
    assert "non-empty string" in result


def test_execute_tool_github_validation() -> None:
    result = execute_tool("github_pr_overview", {"repo": "owner/repo", "pr_number": "12"})
    assert "must be an integer" in result


def test_execute_tool_jenkins_validation() -> None:
    result = execute_tool("jenkins_recent_builds", {"job_name": "", "limit": 5})
    assert "non-empty string" in result


def test_execute_tool_jenkins_log_validation() -> None:
    result = execute_tool("jenkins_build_log", {"job_name": "job-a", "build_number": "12"})
    assert "must be an integer" in result


def test_run_turn_executes_tool_then_returns_final(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_call_ollama(prompt: str, model: str) -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            return json.dumps(
                {"type": "tool_call", "tool": "read_file", "args": {"path": "README.md"}}
            )
        return json.dumps({"type": "final", "content": "done"})

    monkeypatch.setattr(agent_runtime, "call_ollama", fake_call_ollama)
    monkeypatch.setattr("app.tooling.read_file", lambda path: "file content")

    messages = [{"role": "user", "content": "show me readme"}]
    result = agent_runtime.run_turn(messages, model="llama3")

    assert result == "done"
    assert calls["count"] == 2


def test_call_ollama_retries_and_fails(monkeypatch) -> None:
    def always_fail(*args, **kwargs):  # noqa: ANN002, ANN003
        raise ollama_client.requests.RequestException("boom")

    monkeypatch.setattr(ollama_client.requests, "post", always_fail)
    monkeypatch.setattr(ollama_client.settings, "ollama_retries", 2)
    monkeypatch.setattr(ollama_client.time, "sleep", lambda *_: None)

    try:
        ollama_client.call_ollama("test", "llama3")
    except RuntimeError as exc:
        assert "failed after 2 retries" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError when Ollama call fails.")
