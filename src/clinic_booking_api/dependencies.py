from datetime import datetime


def get_now() -> datetime:
    """The current time. Endpoints take it through Depends so tests can fix it."""
    return datetime.now()
