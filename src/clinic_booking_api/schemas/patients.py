from pydantic import BaseModel, ConfigDict
from typing import Literal
from .common import ClinicDateTime
import uuid


class PatientAppointment(BaseModel):
    id: uuid.UUID
    start_time: ClinicDateTime
    end_time: ClinicDateTime
    status: Literal["booked"]
    doctor_id: int
    doctor_name: str
    model_config = ConfigDict(from_attributes=True)