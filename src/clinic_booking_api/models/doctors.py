from sqlalchemy import true
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Doctor(Base):
    __tablename__ = "doctors"
    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str]
    middle_name: Mapped[str | None]
    last_name: Mapped[str]
    specialization: Mapped[str]
    is_active: Mapped[bool] = mapped_column(server_default=true(), default=True)
