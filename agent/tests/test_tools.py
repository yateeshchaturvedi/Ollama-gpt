"""Smoke tests for local tools (run_shell, read_file, write_file).

These tests patch security guards to use controlled values.
"""
from pathlib import Path
from unittest.mock import patch

from app.tools.local_tools import read_file, run_shell, write_file

_TEST_TMPDIR = Path(__file__).parent.parent / ".test_tmp"
_TEST_TMPDIR.mkdir(exist_ok=True)


def test_run_shell_returns_output() -> None:
    # On Windows, 'echo' is a shell built-in — use cmd /c echo via a 'cmd' prefix
    with patch("app.security.ALLOWED_SHELL_PREFIXES", ["cmd"]):
        output = run_shell("cmd /c echo hello")
    assert "hello" in output


def test_run_shell_blocked_command() -> None:
    # python -c must be blocked by the new default allowlist
    with patch("app.security.ALLOWED_SHELL_PREFIXES", ["echo", "ls"]):
        result = run_shell("python -c \"print('hi')\"")
    assert "blocked" in result.lower()


def test_read_file_missing() -> None:
    safe_dir = _TEST_TMPDIR / "rfile_workspace"
    safe_dir.mkdir(exist_ok=True)
    missing = safe_dir / "missing-file.txt"
    with patch("app.security.SAFE_WORKSPACE_ROOT", safe_dir.resolve()):
        result = read_file(str(missing))
    assert "File not found" in result


def test_write_then_read_file() -> None:
    safe_dir = _TEST_TMPDIR / "wfile_workspace"
    safe_dir.mkdir(exist_ok=True)
    target = safe_dir / "example.txt"
    with patch("app.security.SAFE_WORKSPACE_ROOT", safe_dir.resolve()):
        write_result = write_file({"path": str(target), "content": "abc"})
        assert "file written" in write_result
        assert read_file(str(target)) == "abc"
