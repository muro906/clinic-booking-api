"""Tests for PatientAppointment, the item returned by the patient listing.

The listing is unauthenticated, so the most important test is that nothing
beyond the minimized fields can appear in it.
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from clinic_booking_api.schemas.patients import PatientAppointment

START = datetime(2026, 11, 2, 7, 0, tzinfo=UTC)  # 10:00 in Nairobi
END = datetime(2026, 11, 2, 7, 30, tzinfo=UTC)  # 10:30 in Nairobi


def make_listing_row(**overrides):
    """A fake query result row, with extra private columns that must not leak."""
    fields = {
        "id": uuid.uuid4(),
        "start_time": START,
        "end_time": END,
        "status": "booked",
        "doctor_id": 1,
        "doctor_name": "Elaine Maina",
        # Private data a careless query might select. None of it may be returned.
        "patient_id": uuid.uuid4(),
        "name": "Amina Hassan",
        "phone_e164": "+254712345678",
        "email": "amina@clinic.co.ke",
        "token_hash": "abc123",
        "cancel_reason": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_listing_item_contains_only_minimized_fields():
    data = PatientAppointment.model_validate(make_listing_row()).model_dump()
    assert set(data) == {
        "id",
        "start_time",
        "end_time",
        "status",
        "doctor_id",
        "doctor_name",
    }


def test_listing_item_times_are_in_clinic_time():
    item = PatientAppointment.model_validate(make_listing_row())
    data = item.model_dump(mode="json")
    assert data["start_time"] == "2026-11-02T10:00:00+03:00"
    assert data["end_time"] == "2026-11-02T10:30:00+03:00"


def test_listing_item_includes_doctor_name():
    item = PatientAppointment.model_validate(make_listing_row())
    assert item.doctor_name == "Elaine Maina"


def test_listing_item_rejects_cancelled_status():
    # The listing only ever returns booked appointments.
    with pytest.raises(ValidationError):
        PatientAppointment.model_validate(make_listing_row(status="cancelled"))


def test_listing_item_requires_doctor_name():
    row = make_listing_row()
    del row.doctor_name
    with pytest.raises(ValidationError):
        PatientAppointment.model_validate(row)
