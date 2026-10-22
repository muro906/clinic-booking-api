import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from clinic_booking_api.database import get_db
from clinic_booking_api.dependencies import DbSession, Now
from clinic_booking_api.schemas.doctors import AvailabilityOut, DoctorOut
from clinic_booking_api.services.availability import get_availability
from clinic_booking_api.services.doctors import list_active_doctors

router = APIRouter(prefix="/doctors", tags=["doctors"])


@router.get("", response_model=list[DoctorOut])
async def get_doctors(db: Annotated[AsyncSession, Depends(get_db)]):
    return await list_active_doctors(db)


@router.get("/{doctor_id}/availability", response_model=AvailabilityOut)
async def get_doctor_availability(
    doctor_id: int,
    date: Annotated[dt.date, Query(description="The day to check, as YYYY-MM-DD.")],
    db: DbSession,
    now: Now,
) -> AvailabilityOut:
    """Free 30-minute slots for one doctor on one day, in the clinic's timezone."""
    return await get_availability(db, doctor_id, date, now)
