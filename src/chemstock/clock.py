from datetime import date


def get_today() -> date:
    """Return today's date.

    It is a FastAPI dependency so tests can replace it with a fixed date.
    Note: this is the server's local date (UTC inside Docker).
    """
    return date.today()
