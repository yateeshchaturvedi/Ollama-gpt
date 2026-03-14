from pathlib import Path

from tools import read_file, run_shell, write_file


def test_run_shell_returns_output() -> None:
    output = run_shell("python -c \"print('hello')\"")
    assert "hello" in output


def test_read_file_missing() -> None:
    result = read_file("missing-file.txt")
    assert "File not found" in result


def test_write_then_read_file() -> None:
    target_dir = Path(".test_artifacts")
    target = target_dir / "example.txt"
    target_dir.mkdir(exist_ok=True)
    write_result = write_file({"path": str(target), "content": "abc"})
    assert "file written" in write_result
    assert read_file(str(target)) == "abc"
