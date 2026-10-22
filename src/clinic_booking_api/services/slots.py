from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from clinic_booking_api.config import get_settings

SLOT_MINUTES = 30
SLOT_LENGTH = timedelta(minutes=SLOT_MINUTES)
BOOKING_LEAD_TIME = timedelta(hours=1)


def clinic_timezone() -> ZoneInfo:
    return ZoneInfo(get_settings().clinic_timezone)


def minutes_since_midnight(value: time) -> int:
    return value.hour * 60 + value.minute


def slots_in_window(day: date, start: time, end: time, tz: ZoneInfo) -> list[datetime]:
    """
    Define start time of every grid slot  that fit entirely within [start, end]

    The window's start is rounded up to the grid, so 10:15 gives a first slot of 10:30. You'll keep a slot if it ends befor or at the end of the window
    """
    start_minutes = minutes_since_midnight(start)
    end_minutes = minutes_since_midnight(end)

    first = -(-start_minutes // SLOT_MINUTES) * SLOT_MINUTES
    last = end_minutes - SLOT_MINUTES
    return [
        datetime.combine(day, time(minute // 60, minute % 60), tzinfo=tz)
        for minute in range(first, last + 1, SLOT_MINUTES)
    ]


def is_on_grid(local_start: datetime) -> bool:
    """True if the clinic's time is at :00 or :30"""
    return (
        local_start.minute % SLOT_MINUTES == 0
        and local_start.second == 0
        and local_start.microsecond == 0
    )


def fits_in_window(local_start: datetime, start: time, end: time) -> bool:
    """Returns True if a slot starting at local_start fits within time window"""
    slot_start = local_start.hour * 60 + local_start.second
    return (
        minutes_since_midnight(start) <= slot_start
        and minutes_since_midnight(end) >= slot_start + SLOT_MINUTES
    )
