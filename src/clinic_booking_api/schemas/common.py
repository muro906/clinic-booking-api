from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import PlainSerializer

from clinic_booking_api.config import get_settings


def to_clinic_time(value: datetime) -> datetime:
    return value.astimezone(ZoneInfo(get_settings().clinic_timezone))


ClinicDateTime = Annotated[datetime, PlainSerializer(to_clinic_time)]
