from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from clinic_booking_api.database import get_db
from clinic_booking_api.schemas.doctors import DoctorOut
from clinic_booking_api.services.doctors import list_active_doctors

router = APIRouter(prefix="/doctors", tags=["doctors"])


@router.get("", response_model=list[DoctorOut])
async def get_doctors(db: Annotated[AsyncSession, Depends(get_db)]):
    return await list_active_doctors(db)
