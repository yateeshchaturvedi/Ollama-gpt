import shlex
import subprocess  # nosec B404
from pathlib import Path
from typing import TypedDict

from app.security import is_command_allowed, is_within_workspace


class WriteFilePayload(TypedDict):
    path: str
    content: str


def run_shell(command: str) -> str:
    """Run a shell command and return stdout/stderr."""
    try:
        if not is_command_allowed(command):
            return "Shell command blocked by allowlist policy."
        argv = shlex.split(command, posix=True)
        if not argv:
            return "Shell command blocked: empty command."
        result = subprocess.run(
            argv,  # nosec B603
            capture_output=True,
            text=True,
            check=False,
        )
        output = (result.stdout or "") + (result.stderr or "")
        if output.strip():
            return output
        return f"command completed with exit code {result.returncode}"
    except subprocess.SubprocessError as exc:
        return f"Shell execution error: {exc}"
    except OSError as exc:
        return f"OS error while running command: {exc}"
    except ValueError as exc:
        return f"Invalid command: {exc}"
    except Exception as exc:
        return f"Unexpected shell error: {exc}"


def read_file(path: str) -> str:
    """Read a UTF-8 text file and return its content."""
    try:
        if not is_within_workspace(path):
            return "File read blocked: path is outside SAFE_WORKSPACE_ROOT."
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"File not found: {path}"
    except PermissionError:
        return f"Permission denied while reading: {path}"
    except IsADirectoryError:
        return f"Path is a directory, not a file: {path}"
    except UnicodeDecodeError:
        return f"Failed to decode file as UTF-8: {path}"
    except OSError as exc:
        return f"File read error: {exc}"
    except Exception as exc:
        return f"Unexpected read error: {exc}"


def write_file(data: WriteFilePayload) -> str:
    """Write UTF-8 text content to a file path."""
    try:
        path = data["path"]
        content = data["content"]
        if not is_within_workspace(path):
            return "File write blocked: path is outside SAFE_WORKSPACE_ROOT."

        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        return f"file written: {path}"
    except KeyError as exc:
        return f"Missing required write_file field: {exc}"
    except PermissionError:
        return f"Permission denied while writing: {data.get('path', '<missing>')}"
    except IsADirectoryError:
        return f"Path is a directory, not a file: {data.get('path', '<missing>')}"
    except OSError as exc:
        return f"File write error: {exc}"
    except Exception as exc:
        return f"Unexpected write error: {exc}"
