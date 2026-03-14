"""Backward-compatible entrypoint for the Slack bot worker."""

from app.slack_runtime import main


if __name__ == "__main__":
    main()

