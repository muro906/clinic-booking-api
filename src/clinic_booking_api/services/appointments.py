"""Booking, cancelling and rescheduling appointments.

Rules that depend on the current time or on other tables are checked here:
the 30-minute grid, not in the past, the 1-hour lead time, an active doctor,
and working hours.

Rules that must hold even under concurrent requests are enforced by the
database: the partial unique indexes allow one booked appointment per doctor
per slot, and one per patient per slot. This module attempts the write and
turns a violation into a 409. It never checks first and then inserts, because
two requests could both pass the check.
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from clinic_booking_api.errors import BookingRuleError, ConflictError, NotFoundError
from clinic_booking_api.models import Appointment, Patient, WorkingHours
from clinic_booking_api.schemas.appointments import (
    AppointmentCreate,
    AppointmentCreated,
    AppointmentOut,
)
from clinic_booking_api.services.doctors import get_active_doctor
from clinic_booking_api.services.slots import (
    BOOKING_LEAD_TIME,
    SLOT_LENGTH,
    clinic_timezone,
    fits_in_window,
    is_on_grid,
)

BOOKING_CONFLICT_CONSTRAINTS = {"uq_doctor_slot_booked", "uq_patient_slot_booked"}
CHECK_CONSTRAINTS = {
    "ck_slot_duration",
    "ck_slot_aligned",
    "ck_status",
    "ck_cancel_fields",
}


# --- Tokens -------------------------------------------------------------------


def generate_token() -> str:
    """A random secret with 256 bits of entropy, returned to the patient once."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Only the SHA-256 hash is stored, so a database leak exposes no live tokens.

    A fast hash is safe here because the token is random, not a guessable password.
    """
    return hashlib.sha256(token.encode()).hexdigest()


# --- Validation shared by booking and rescheduling ----------------------------


async def validate_slot(
    db: AsyncSession, doctor_id: int, start: datetime, now: datetime
) -> None:
    """Raise if `start` is not a bookable slot for this doctor right now."""
    local_start = start.astimezone(clinic_timezone())

    if not is_on_grid(local_start):
        raise BookingRuleError(
            "off_grid",
            "Appointments start on the hour or half hour, for example 10:00 or 10:30.",
        )
    if start < now:
        raise BookingRuleError("in_the_past", "The requested time is in the past.")
    if start < now + BOOKING_LEAD_TIME:
        raise BookingRuleError(
            "too_soon", "Appointments must be booked at least 1 hour in advance."
        )

    await get_active_doctor(db, doctor_id)

    windows = await db.scalars(
        select(WorkingHours).where(
            WorkingHours.doctor_id == doctor_id,
            WorkingHours.weekday == local_start.weekday(),
        )
    )
    if not any(fits_in_window(local_start, w.start_time, w.end_time) for w in windows):
        raise BookingRuleError(
            "outside_working_hours", "The doctor is not working at the requested time."
        )


# --- Database helpers -----------------------------------------------------------


def _constraint_name(exc: IntegrityError) -> str | None:
    """The name of the constraint that rejected the write, if we can find it.

    asyncpg exposes it on the original exception; the message is a fallback.
    """
    cause = getattr(exc.orig, "__cause__", None)
    name = getattr(cause, "constraint_name", None)
    if name:
        return name
    message = str(exc.orig)
    known = BOOKING_CONFLICT_CONSTRAINTS | CHECK_CONSTRAINTS
    return next((candidate for candidate in known if candidate in message), None)


async def _commit_or_raise(db: AsyncSession) -> None:
    """Commit, turning constraint violations into API errors."""
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        name = _constraint_name(exc)
        if name in BOOKING_CONFLICT_CONSTRAINTS:
            # One generic message for both rules, so the API never reveals
            # whether a phone number already has a booking at that time.
            raise ConflictError(
                "booking_conflict", "This booking conflicts with an existing booking."
            ) from exc
        if name in CHECK_CONSTRAINTS:
            # Backstop: the service validates first, so this should not happen.
            raise BookingRuleError(
                "invalid_slot", "The requested time is not a valid appointment slot."
            ) from exc
        raise


async def _find_or_create_patient(
    db: AsyncSession, booking: AppointmentCreate
) -> uuid.UUID:
    """Reuse the patient row for this phone and normalized name, or create one.

    INSERT ... ON CONFLICT DO NOTHING is safe under concurrency: if two first
    bookings by the same person arrive together, one inserts and the other
    finds the committed row.
    """
    inserted_id = await db.scalar(
        insert(Patient)
        .values(
            name=booking.name,
            name_normalized=booking.name_normalized,
            phone_e164=booking.phone,
            email=booking.email,
        )
        .on_conflict_do_nothing(constraint="uq_patient_contact")
        .returning(Patient.id)
    )
    if inserted_id is not None:
        return inserted_id

    # The first booker's display name and email are kept; later bookings reuse the row.
    return await db.scalar(
        select(Patient.id).where(
            Patient.phone_e164 == booking.phone,
            Patient.name_normalized == booking.name_normalized,
        )
    )


async def _get_owned_appointment(
    db: AsyncSession, appointment_id: uuid.UUID, token: str
) -> Appointment:
    """Load an appointment the caller can prove they own, locking its row.

    A wrong token gives the same 404 as an unknown id, so ids cannot be probed.
    The row lock stops a concurrent cancel and reschedule of the same
    appointment from interleaving.
    """
    appointment = await db.scalar(
        select(Appointment).where(Appointment.id == appointment_id).with_for_update()
    )
    if appointment is None or not hmac.compare_digest(
        appointment.token_hash, hash_token(token)
    ):
        raise NotFoundError("appointment_not_found", "Appointment not found.")
    return appointment


# --- Public operations ------------------------------------------------------------


async def book_appointment(
    db: AsyncSession, booking: AppointmentCreate, now: datetime
) -> AppointmentCreated:
    await validate_slot(db, booking.doctor_id, booking.start_time, now)

    patient_id = await _find_or_create_patient(db, booking)
    token = generate_token()
    appointment = Appointment(
        doctor_id=booking.doctor_id,
        patient_id=patient_id,
        start_time=booking.start_time,
        end_time=booking.start_time + SLOT_LENGTH,
        status="booked",
        cancel_reason=None,
        cancelled_at=None,
        token_hash=hash_token(token),
    )
    db.add(appointment)
    await _commit_or_raise(db)

    # The plain token appears in this one response and is never stored.
    return AppointmentCreated(
        **AppointmentOut.model_validate(appointment).model_dump(), token=token
    )


async def cancel_appointment(
    db: AsyncSession,
    appointment_id: uuid.UUID,
    token: str,
    reason: str,
    now: datetime,
) -> AppointmentOut:
    appointment = await _get_owned_appointment(db, appointment_id, token)

    if appointment.status == "cancelled":
        raise ConflictError(
            "already_cancelled", "This appointment is already cancelled."
        )
    if appointment.start_time <= now:
        raise BookingRuleError(
            "already_started", "This appointment has already started."
        )

    # A status change, not a delete: the row leaves the partial unique indexes,
    # which frees the slot, and the history is kept.
    appointment.status = "cancelled"
    appointment.cancel_reason = reason
    appointment.cancelled_at = now
    await db.commit()

    return AppointmentOut.model_validate(appointment)


async def reschedule_appointment(
    db: AsyncSession,
    appointment_id: uuid.UUID,
    token: str,
    new_start: datetime,
    now: datetime,
) -> AppointmentOut:
    appointment = await _get_owned_appointment(db, appointment_id, token)

    if appointment.status == "cancelled":
        raise ConflictError(
            "appointment_cancelled", "A cancelled appointment cannot be rescheduled."
        )
    if appointment.start_time <= now:
        raise BookingRuleError(
            "already_started", "This appointment has already started."
        )
    if new_start == appointment.start_time:
        raise BookingRuleError(
            "same_slot", "The appointment is already at the requested time."
        )

    # Same doctor only, validated exactly like a fresh booking.
    await validate_slot(db, appointment.doctor_id, new_start, now)

    # One transaction: if the new slot is taken, the commit fails, everything
    # rolls back, and the original appointment is untouched.
    appointment.start_time = new_start
    appointment.end_time = new_start + SLOT_LENGTH
    await _commit_or_raise(db)

    return AppointmentOut.model_validate(appointment)
