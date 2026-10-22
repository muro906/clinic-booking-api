from datetime import datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from clinic_booking_api.database import get_db


def get_now() -> datetime:
    """The current time. Endpoints take it through Depends so tests can fix it."""
    return datetime.now()


DbSession = Annotated[AsyncSession, Depends(get_db)]
Now = Annotated[datetime, Depends(get_now)]
