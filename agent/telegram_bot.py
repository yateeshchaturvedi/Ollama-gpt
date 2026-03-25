"""Backward-compatible entrypoint for the Telegram bot worker."""

from app.telegram_runtime import main


if __name__ == "__main__":
    main()
