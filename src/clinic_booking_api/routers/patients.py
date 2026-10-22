import uuid

from fastapi import APIRouter

from clinic_booking_api.dependencies import DbSession, Now
from clinic_booking_api.schemas.patients import PatientAppointment
from clinic_booking_api.services.patients import list_upcoming_appointments

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("/{patient_id}/appointments", response_model=list[PatientAppointment])
async def get_patient_appointments(
    patient_id: uuid.UUID, db: DbSession, now: Now
) -> list[PatientAppointment]:
    """The patient's upcoming booked appointments, earliest first."""
    return await list_upcoming_appointments(db, patient_id, now)
