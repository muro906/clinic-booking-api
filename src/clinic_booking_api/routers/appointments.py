import uuid
from typing import Annotated

from fastapi import APIRouter, Header, status

from clinic_booking_api.dependencies import DbSession, Now
from clinic_booking_api.schemas.appointments import (
    AppointmentCreate,
    AppointmentCreated,
    AppointmentOut,
    CancelRequest,
    RescheduleRequest,
)
from clinic_booking_api.services.appointments import (
    book_appointment,
    cancel_appointment,
    reschedule_appointment,
)

router = APIRouter(prefix="/appointments", tags=["appointments"])

# The token travels in a header, never in the URL, because URLs end up in logs.
BookingToken = Annotated[
    str,
    Header(
        alias="X-Booking-Token",
        description="The token returned once when the appointment was booked.",
    ),
]


@router.post("", response_model=AppointmentCreated, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    booking: AppointmentCreate, db: DbSession, now: Now
) -> AppointmentCreated:
    """Book a 30-minute slot. The response contains the booking token, shown only once."""
    return await book_appointment(db, booking, now)


@router.patch("/{appointment_id}/cancel", response_model=AppointmentOut)
async def cancel(
    appointment_id: uuid.UUID,
    body: CancelRequest,
    token: BookingToken,
    db: DbSession,
    now: Now,
) -> AppointmentOut:
    """Cancel an appointment with a reason. The slot becomes bookable again."""
    return await cancel_appointment(db, appointment_id, token, body.reason, now)


@router.patch("/{appointment_id}/reschedule", response_model=AppointmentOut)
async def reschedule(
    appointment_id: uuid.UUID,
    body: RescheduleRequest,
    token: BookingToken,
    db: DbSession,
    now: Now,
) -> AppointmentOut:
    """Move an appointment to a new slot with the same doctor."""
    return await reschedule_appointment(db, appointment_id, token, body.start_time, now)
