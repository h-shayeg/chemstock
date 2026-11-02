from datetime import UTC, date, datetime


def get_today() -> date:
    """Return today's date.

    It is a FastAPI dependency so tests can replace it with a fixed date.
    Note: this is the server's local date (UTC inside Docker).
    """
    return date.today()


def get_now() -> datetime:
    """Return the current time in UTC (a FastAPI dependency, like get_today)."""
    return datetime.now(UTC)
