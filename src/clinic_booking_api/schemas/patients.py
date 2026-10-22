import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .common import ClinicDateTime


class PatientAppointment(BaseModel):
    id: uuid.UUID
    start_time: ClinicDateTime
    end_time: ClinicDateTime
    status: Literal["booked"]
    doctor_id: int
    doctor_name: str
    model_config = ConfigDict(from_attributes=True)
