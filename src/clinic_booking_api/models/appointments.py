import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# Both partial indexes only count active bookings. Cancelling an appointment removes that row from index which frees slot
BOOKED_ONLY = text("status = 'booked'")


class Appointment(Base):
    """Every booking, past and present. Cancelled rows stay for historical purposes"""

    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint(
            "end_time = start_time + interval '30 minutes'", name="ck_slot_duration"
        ),
        # Start must sit on the valid 30-minute grid(:00 0r :30, zero seconds)
        CheckConstraint(
            "mod(extract(epoch from start_time), 1800) = 0", name="ck_slot_aligned"
        ),
        CheckConstraint("status IN ('booked', 'cancelled')", name="ck_status"),
        CheckConstraint(
            "status <> 'cancelled'"
            " OR (cancel_reason IS NOT NULL AND cancelled_at IS NOT NULL) ",
            name="ck_cancel_fields",
        ),
        # No double booking at doctors. Also serve the availability query. Create a partial index on doctor_id and start_time columns
        Index(
            "uq_doctor_slot_booked",
            "doctor_id",
            "start_time",
            unique=True,
            postgresql_where=BOOKED_ONLY,
        ),
        # One person cannot hold two different bookings at the same time. Also server as listing query
        Index(
            "uq_patient_slot_booked",
            "patient_id",
            "start_time",
            unique=True,
            postgresql_where=BOOKED_ONLY,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(default="booked", server_default="booked")
    cancel_reason: Mapped[str | None]
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_hash: Mapped[str]  # SHA-256 of the token, token itself is never stored
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
