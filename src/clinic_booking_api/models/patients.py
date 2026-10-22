import uuid
from datetime import datetime

from sqlalchemy import DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Patient(Base):
    """Minimal contact record. One row per person as the clinic knows them."""

    __tablename__ = "patients"
    __table_args__ = (
        # The contact key: the same phone and normalized name reuse one row,
        # while a family member on the same phone with a different name gets their own.
        UniqueConstraint("phone_e164", "name_normalized", name="uq_patient_contact"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str]  # as the patient typed it, for display
    name_normalized: Mapped[str]  # casefolded, trimmed, spaces collapsed
    phone_e164: Mapped[str]  # for example +254712345678
    email: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
