"""Purpose of service is such that if give a day, doctor and current time, compute the available slots

Slots are computed at request time so there's no need to keep a slots table in sync
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from clinic_booking_api.models.appointments import Appointment
from clinic_booking_api.models.working_hours import WorkingHours
from clinic_booking_api.schemas.doctors import AvailabilityOut, Slot
from clinic_booking_api.services.doctors import get_active_doctor
from clinic_booking_api.services.slots import (
    BOOKING_LEAD_TIME,
    SLOT_LENGTH,
    clinic_timezone,
    slots_in_window,
)


async def get_availability(
    db: AsyncSession, doctor_id: int, day: date, now: datetime
) -> AvailabilityOut:
    await get_active_doctor(db, doctor_id)
    tz = clinic_timezone()
    stmt = select(WorkingHours).where(
        WorkingHours.doctor_id == doctor_id, WorkingHours.weekday == day.weekday()
    )
    windows = await db.scalars(stmt)

    candidates = {
        slot
        for window in windows
        for slot in slots_in_window(day, window.start_time, window.end_time, tz)
    }
    # a set, so overlapping windows don't produce duplicate slots

    # Filter out booked slots

    day_start = datetime.combine(day, time(0), tzinfo=tz)
    day_end = day_start + timedelta(days=1)

    # Get set of slots already booked that day
    booked = set(
        await db.scalars(
            select(Appointment.start_time).where(
                Appointment.doctor_id == doctor_id,
                Appointment.status == "booked",
                Appointment.start_time >= day_start,
                Appointment.end_time < day_end,
            )
        )
    )

    # 3. Drop booked slots or anything too close too be booked. Constraint was you can't book less than or equal an hour before

    # Get earliest booking
    earliest = now + BOOKING_LEAD_TIME
    free = sorted(
        slot for slot in candidates if not slot in booked and slot >= earliest
    )

    return AvailabilityOut(
        doctor_id=doctor_id,
        date=day,
        timezone=tz.key,
        slots=[Slot(start_time=slot, end_time=slot + SLOT_LENGTH) for slot in free],
    )
