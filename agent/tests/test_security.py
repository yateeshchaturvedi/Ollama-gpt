"""Unit tests for app.security module."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from app.security import (
    audit_tool_call,
    is_command_allowed,
    is_confirmation_valid,
    is_rate_limited,
    is_within_workspace,
    truncate_shell_output,
)

# Use a stable temp dir inside the project workspace to avoid Windows %TEMP% ACL issues
_TEST_TMPDIR = Path(__file__).parent.parent / ".test_tmp"
_TEST_TMPDIR.mkdir(exist_ok=True)


# ── is_within_workspace ────────────────────────────────────────────────────────

class TestIsWithinWorkspace:
    def test_exact_workspace_root_is_allowed(self):
        safe_dir = _TEST_TMPDIR / "workspace_exact"
        safe_dir.mkdir(exist_ok=True)
        with patch("app.security.SAFE_WORKSPACE_ROOT", safe_dir.resolve()):
            assert is_within_workspace(str(safe_dir)) is True

    def test_subdirectory_is_allowed(self):
        safe_dir = _TEST_TMPDIR / "workspace_sub"
        safe_dir.mkdir(exist_ok=True)
        sub = safe_dir / "subdir" / "file.txt"
        with patch("app.security.SAFE_WORKSPACE_ROOT", safe_dir.resolve()):
            assert is_within_workspace(str(sub)) is True

    def test_parent_directory_is_blocked(self):
        safe_dir = _TEST_TMPDIR / "workspace_parent"
        safe_dir.mkdir(exist_ok=True)
        with patch("app.security.SAFE_WORKSPACE_ROOT", safe_dir.resolve()):
            assert is_within_workspace(str(safe_dir.parent)) is False

    def test_arbitrary_path_is_blocked(self):
        safe_dir = _TEST_TMPDIR / "workspace_arb"
        safe_dir.mkdir(exist_ok=True)
        with patch("app.security.SAFE_WORKSPACE_ROOT", safe_dir.resolve()):
            assert is_within_workspace("C:/Windows/System32") is False

    def test_path_traversal_attempt_is_blocked(self):
        safe_dir = _TEST_TMPDIR / "workspace_trav"
        safe_dir.mkdir(exist_ok=True)
        evil = str(safe_dir / ".." / ".." / "etc" / "passwd")
        with patch("app.security.SAFE_WORKSPACE_ROOT", safe_dir.resolve()):
            assert is_within_workspace(evil) is False


# ── is_command_allowed ─────────────────────────────────────────────────────────

class TestIsCommandAllowed:
    def test_allowed_prefix_ls(self):
        with patch("app.security.ALLOWED_SHELL_PREFIXES", ["ls", "dir", "echo"]):
            assert is_command_allowed("ls -la") is True

    def test_allowed_prefix_echo(self):
        with patch("app.security.ALLOWED_SHELL_PREFIXES", ["ls", "echo"]):
            assert is_command_allowed("echo hello world") is True

    def test_blocked_command(self):
        with patch("app.security.ALLOWED_SHELL_PREFIXES", ["ls", "echo"]):
            assert is_command_allowed("rm -rf /") is False

    def test_python_c_is_blocked_by_default(self):
        """Critical: python -c must NOT be in the default allowlist."""
        with patch("app.security.ALLOWED_SHELL_PREFIXES", ["ls", "dir", "pwd", "echo", "cat", "type"]):
            assert is_command_allowed("python -c 'import os'") is False

    def test_empty_command_is_blocked(self):
        with patch("app.security.ALLOWED_SHELL_PREFIXES", ["ls"]):
            assert is_command_allowed("") is False
            assert is_command_allowed("   ") is False

    def test_case_insensitive_match(self):
        with patch("app.security.ALLOWED_SHELL_PREFIXES", ["ls"]):
            assert is_command_allowed("LS -la") is True


# ── is_rate_limited ────────────────────────────────────────────────────────────

class TestIsRateLimited:
    def test_not_rate_limited_under_threshold(self):
        with (
            patch("app.security.TOOL_RATE_LIMIT_COUNT", 5),
            patch("app.security.TOOL_RATE_LIMIT_WINDOW_SECONDS", 60),
            patch("app.security._tool_calls", []),
        ):
            for _ in range(4):
                assert is_rate_limited() is False

    def test_rate_limited_at_threshold(self):
        with (
            patch("app.security.TOOL_RATE_LIMIT_COUNT", 3),
            patch("app.security.TOOL_RATE_LIMIT_WINDOW_SECONDS", 60),
            patch("app.security._tool_calls", []),
        ):
            assert is_rate_limited() is False  # call 1
            assert is_rate_limited() is False  # call 2
            assert is_rate_limited() is False  # call 3
            assert is_rate_limited() is True   # call 4 — over limit

    def test_expired_calls_are_evicted(self):
        """Calls older than the window should not count."""
        old_time = time.monotonic() - 120  # 2 minutes ago
        with (
            patch("app.security.TOOL_RATE_LIMIT_COUNT", 2),
            patch("app.security.TOOL_RATE_LIMIT_WINDOW_SECONDS", 60),
            patch("app.security._tool_calls", [old_time, old_time]),
        ):
            # Both old calls should be evicted, so we're under the limit
            assert is_rate_limited() is False

    def test_thread_safety(self):
        """Concurrent calls must not corrupt the rate-limiter state."""
        results: list[bool] = []
        lock = threading.Lock()

        with (
            patch("app.security.TOOL_RATE_LIMIT_COUNT", 10),
            patch("app.security.TOOL_RATE_LIMIT_WINDOW_SECONDS", 60),
            patch("app.security._tool_calls", []),
        ):
            def call():
                result = is_rate_limited()
                with lock:
                    results.append(result)

            threads = [threading.Thread(target=call) for _ in range(15)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        # First 10 calls should not be rate limited; last 5 should be
        not_limited = sum(1 for r in results if not r)
        limited = sum(1 for r in results if r)
        assert not_limited == 10
        assert limited == 5


# ── audit_tool_call ────────────────────────────────────────────────────────────

class TestAuditToolCall:
    def test_writes_valid_json_entry(self):
        log_path = _TEST_TMPDIR / "test_audit.log"
        log_path.unlink(missing_ok=True)  # fresh file each run
        import logging
        from logging.handlers import RotatingFileHandler
        test_logger = logging.getLogger("tool_audit_test")
        test_logger.handlers.clear()
        handler = RotatingFileHandler(str(log_path), maxBytes=1_000_000, backupCount=1)
        handler.setFormatter(logging.Formatter("%(message)s"))
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)
        test_logger.propagate = False

        with patch("app.security._audit_logger", test_logger):
            audit_tool_call("read_file", True, "ok", {"path": "/workspace/x.txt"})

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["tool"] == "read_file"
        assert entry["allowed"] is True
        assert entry["reason"] == "ok"
        assert "path" in entry["arg_keys"]


# ── is_confirmation_valid ──────────────────────────────────────────────────────

class TestIsConfirmationValid:
    def test_valid_confirmation(self):
        with (
            patch("app.security.DANGEROUS_ACTIONS_REQUIRE_CONFIRMATION", True),
            patch("app.security.DANGEROUS_CONFIRMATION_TOKEN", "CONFIRM"),
        ):
            assert is_confirmation_valid({"confirmation": "CONFIRM"}) is True

    def test_invalid_confirmation(self):
        with (
            patch("app.security.DANGEROUS_ACTIONS_REQUIRE_CONFIRMATION", True),
            patch("app.security.DANGEROUS_CONFIRMATION_TOKEN", "CONFIRM"),
        ):
            assert is_confirmation_valid({"confirmation": "wrong"}) is False
            assert is_confirmation_valid({}) is False

    def test_confirmation_not_required(self):
        with patch("app.security.DANGEROUS_ACTIONS_REQUIRE_CONFIRMATION", False):
            assert is_confirmation_valid({}) is True
            assert is_confirmation_valid({"confirmation": "anything"}) is True


# ── truncate_shell_output ──────────────────────────────────────────────────────

class TestTruncateShellOutput:
    def test_short_output_not_truncated(self):
        with patch("app.security.MAX_SHELL_OUTPUT_CHARS", 100):
            result = truncate_shell_output("hello world")
            assert result == "hello world"

    def test_long_output_is_truncated(self):
        with patch("app.security.MAX_SHELL_OUTPUT_CHARS", 10):
            long_output = "a" * 50
            result = truncate_shell_output(long_output)
            assert result.startswith("a" * 10)
            assert "truncated" in result.lower()

    def test_truncated_output_contains_char_count(self):
        with patch("app.security.MAX_SHELL_OUTPUT_CHARS", 20):
            result = truncate_shell_output("x" * 100)
            assert "20" in result
