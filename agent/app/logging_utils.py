import logging


def setup_logging(level: str) -> None:
    """Initialize logging for the application."""
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )

