from datetime import time

from sqlalchemy import SMALLINT, CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import Index

from .base import Base


class WorkingHours(Base):
    __tablename__ = "working_hours"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_working_hours_weekday"),
        CheckConstraint(
            "start_time < end_time", name="ck_working_hours_start_before_end"
        ),
        Index("ix_working_hours_doctor_weekday", "doctor_id", "weekday"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    weekday: Mapped[int] = mapped_column(SMALLINT)
    start_time: Mapped[time]
    end_time: Mapped[time]
