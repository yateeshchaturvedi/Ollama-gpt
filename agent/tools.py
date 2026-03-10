import subprocess


def run_shell(command: str):

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True
        )

        return result.stdout + result.stderr

    except Exception as e:
        return str(e)


def read_file(path: str):

    try:
        with open(path, "r") as f:
            return f.read()

    except Exception as e:
        return str(e)


def write_file(data: dict):

    try:
        path = data["path"]
        content = data["content"]

        with open(path, "w") as f:
            f.write(content)

        return "file written"

    except Exception as e:
        return str(e)