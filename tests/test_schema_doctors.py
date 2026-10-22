"""Tests for DoctorOut, Slot and AvailabilityOut."""

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from clinic_booking_api.schemas.doctors import AvailabilityOut, DoctorOut, Slot

START = datetime(2026, 11, 2, 7, 0, tzinfo=UTC)  # 10:00 in Nairobi
END = datetime(2026, 11, 2, 7, 30, tzinfo=UTC)  # 10:30 in Nairobi


def make_doctor(**overrides):
    """A fake doctor row, including columns DoctorOut must not expose."""
    fields = {
        "id": 1,
        "first_name": "Elaine",
        "middle_name": None,
        "last_name": "Maina",
        "specialization": "General Practice",
        "is_active": True,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


# --- DoctorOut --------------------------------------------------------------


def test_doctor_out_exposes_only_declared_fields():
    data = DoctorOut.model_validate(make_doctor()).model_dump()
    assert set(data) == {
        "id",
        "first_name",
        "middle_name",
        "last_name",
        "specialization",
    }
    assert "is_active" not in data


def test_doctor_out_allows_missing_middle_name():
    assert DoctorOut.model_validate(make_doctor(middle_name=None)).middle_name is None


def test_doctor_out_keeps_middle_name():
    doctor = DoctorOut.model_validate(make_doctor(middle_name="Njeri"))
    assert doctor.middle_name == "Njeri"


def test_doctor_out_requires_specialization():
    incomplete = make_doctor()
    del incomplete.specialization
    with pytest.raises(ValidationError):
        DoctorOut.model_validate(incomplete)


# --- Slot -------------------------------------------------------------------


def test_slot_times_are_in_clinic_time():
    data = Slot(start_time=START, end_time=END).model_dump(mode="json")
    assert data == {
        "start_time": "2026-11-02T10:00:00+03:00",
        "end_time": "2026-11-02T10:30:00+03:00",
    }


# --- AvailabilityOut --------------------------------------------------------


def test_availability_out_json_shape():
    availability = AvailabilityOut(
        doctor_id=1,
        date=date(2026, 11, 2),
        timezone="Africa/Nairobi",
        slots=[Slot(start_time=START, end_time=END)],
    )
    data = availability.model_dump(mode="json")

    assert data["doctor_id"] == 1
    assert data["date"] == "2026-11-02"
    assert data["timezone"] == "Africa/Nairobi"
    assert data["slots"] == [
        {
            "start_time": "2026-11-02T10:00:00+03:00",
            "end_time": "2026-11-02T10:30:00+03:00",
        }
    ]


def test_availability_out_allows_no_slots():
    # A day off, or a fully booked day, is a valid answer, not an error.
    availability = AvailabilityOut(
        doctor_id=1,
        date=date(2026, 11, 8),
        timezone="Africa/Nairobi",
        slots=[],
    )
    assert availability.slots == []


def test_availability_out_rejects_invalid_date():
    with pytest.raises(ValidationError):
        AvailabilityOut(
            doctor_id=1,
            date="2026-13-40",
            timezone="Africa/Nairobi",
            slots=[],
        )
