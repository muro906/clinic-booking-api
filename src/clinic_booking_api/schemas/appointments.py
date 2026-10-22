import uuid
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
)

from clinic_booking_api.services.normalization import (
    clean_display_name,
    normalize_name,
    normalize_phone,
)

from .common import ClinicDateTime


# Request Body for Post/appointments endpoint. User can create appointments with doctor by supplying this info
class AppointmentCreate(BaseModel):
    # Must be positive. Clients get it from GET/doctors
    doctor_id: Annotated[int, Field(gt=0)]
    start_time: AwareDatetime
    name: Annotated[
        str, StringConstraints(max_length=100), AfterValidator(clean_display_name)
    ]

    phone: Annotated[
        str, StringConstraints(max_length=25), AfterValidator(normalize_phone)
    ]

    email: EmailStr | None = None

    # Reject unknown fields catching client typos
    model_config = ConfigDict(extra="forbid")

    @property
    def name_normalized(self) -> str:
        return normalize_name(self.name)


# Response Body for response: cancel ,reschedule and base for booking
class AppointmentOut(BaseModel):
    id: uuid.UUID
    doctor_id: int
    patient_id: uuid.UUID
    start_time: ClinicDateTime
    end_time: ClinicDateTime
    status: Literal["booked", "cancelled"]
    cancel_reason: str | None
    cancelled_at: ClinicDateTime | None

    model_config = ConfigDict(from_attributes=True)


# Response body for response: booking
class AppointmentCreated(AppointmentOut):
    token: str


# Handles Request Body to PATCH /appointments/{id}/reschedule
class RescheduleRequest(BaseModel):
    start_time: AwareDatetime
    model_config = ConfigDict(extra="forbid")


# Request Body Class for PATCH /appointments/{id}/cancel
class CancelRequest(BaseModel):
    reason: Annotated[
        str, StringConstraints(min_length=1, max_length=500, strip_whitespace=True)
    ]
    model_config = ConfigDict(extra="forbid")
