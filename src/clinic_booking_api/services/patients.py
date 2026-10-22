"""The patient's upcoming appointments.

The listing is unauthenticated by decision, so it returns only minimized
fields: no contact details, no token, no cancel reason.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from clinic_booking_api.errors import NotFoundError
from clinic_booking_api.models import Appointment, Doctor, Patient
from clinic_booking_api.schemas.patients import PatientAppointment


async def list_upcoming_appointments(
    db: AsyncSession, patient_id: uuid.UUID, now: datetime
) -> list[PatientAppointment]:
    if await db.get(Patient, patient_id) is None:
        raise NotFoundError("patient_not_found", "Patient not found.")

    statement = (
        select(
            Appointment.id,
            Appointment.start_time,
            Appointment.end_time,
            Appointment.status,
            Appointment.doctor_id,
            (Doctor.first_name + " " + Doctor.last_name).label("doctor_name"),
        )
        .join(Doctor, Doctor.id == Appointment.doctor_id)
        .where(
            Appointment.patient_id == patient_id,
            Appointment.status == "booked",  # matches the partial index
            Appointment.start_time >= now,
        )
        .order_by(Appointment.start_time)
    )
    rows = (await db.execute(statement)).all()
    return [PatientAppointment.model_validate(row) for row in rows]
