from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from clinic_booking_api.errors import NotFoundError
from clinic_booking_api.models.doctors import Doctor


# Service func for list_active_doctors | GET /doctors
async def list_active_doctors(db: AsyncSession) -> list[Doctor]:
    stmt = select(Doctor).where(Doctor.is_active.is_(True)).order_by(Doctor.id)

    result = await db.scalars(stmt)
    return list(result)


# Service function that returns active doctor
async def get_active_doctor(db: AsyncSession, doctor_id: int) -> Doctor:
    doctor = await db.get(Doctor, doctor_id)
    if doctor is None or not doctor.is_active:
        raise NotFoundError("doctor_not_found", "Doctor not found")
    return doctor
