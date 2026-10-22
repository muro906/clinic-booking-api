import datetime as dt

from pydantic import BaseModel, ConfigDict

from .common import ClinicDateTime


# Defines working hours for a doctor
class Slot(BaseModel):
    start_time: ClinicDateTime
    end_time: ClinicDateTime


# Part of availability response for GET /doctors/{id}/availability to get list of available time slots for a doctor
class AvailabilityOut(BaseModel):
    doctor_id: int
    date: dt.date
    timezone: str
    slots: list[Slot]


# Part of availabilty response to GET /doctors
class DoctorOut(BaseModel):
    id: int
    first_name: str
    middle_name: str | None
    last_name: str
    specialization: str
    model_config = ConfigDict(from_attributes=True)
