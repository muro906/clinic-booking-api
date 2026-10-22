"""Tests for the appointment schemas other than AppointmentCreate.

Response schemas read attributes (from_attributes=True), so a SimpleNamespace
stands in for a database row. No database is needed.
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from clinic_booking_api.schemas.appointments import (
    AppointmentCreated,
    AppointmentOut,
    CancelRequest,
    RescheduleRequest,
)

START = datetime(2026, 11, 2, 7, 0, tzinfo=UTC)  # 10:00 in Nairobi
END = datetime(2026, 11, 2, 7, 30, tzinfo=UTC)  # 10:30 in Nairobi


def make_appointment(**overrides):
    """A fake appointment row. It includes token_hash, like the real one."""
    fields = {
        "id": uuid.uuid4(),
        "doctor_id": 1,
        "patient_id": uuid.uuid4(),
        "start_time": START,
        "end_time": END,
        "status": "booked",
        "cancel_reason": None,
        "cancelled_at": None,
        "token_hash": "abc123",
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


# --- AppointmentOut ---------------------------------------------------------


def test_appointment_out_never_exposes_token():
    data = AppointmentOut.model_validate(make_appointment()).model_dump()
    assert "token" not in data
    assert "token_hash" not in data


def test_appointment_out_times_are_in_clinic_time():
    data = AppointmentOut.model_validate(make_appointment()).model_dump(mode="json")
    assert data["start_time"] == "2026-11-02T10:00:00+03:00"
    assert data["end_time"] == "2026-11-02T10:30:00+03:00"


def test_appointment_out_booked_has_no_cancellation_details():
    data = AppointmentOut.model_validate(make_appointment()).model_dump(mode="json")
    assert data["cancel_reason"] is None
    assert data["cancelled_at"] is None


def test_appointment_out_cancelled_time_is_in_clinic_time():
    cancelled = make_appointment(
        status="cancelled",
        cancel_reason="Travelling",
        cancelled_at=datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
    )
    data = AppointmentOut.model_validate(cancelled).model_dump(mode="json")
    assert data["status"] == "cancelled"
    assert data["cancel_reason"] == "Travelling"
    assert data["cancelled_at"] == "2026-11-01T15:00:00+03:00"


def test_appointment_out_rejects_unknown_status():
    with pytest.raises(ValidationError):
        AppointmentOut.model_validate(make_appointment(status="pending"))


# --- AppointmentCreated -----------------------------------------------------


def test_appointment_created_includes_token_but_not_hash():
    base = AppointmentOut.model_validate(make_appointment()).model_dump()
    data = AppointmentCreated(**base, token="secret-token").model_dump()
    assert data["token"] == "secret-token"
    assert "token_hash" not in data


def test_appointment_created_requires_a_token():
    # The database row has only token_hash, so building directly from it fails.
    with pytest.raises(ValidationError):
        AppointmentCreated.model_validate(make_appointment())


# --- CancelRequest ----------------------------------------------------------


def test_cancel_reason_is_stripped():
    assert CancelRequest(reason="  emergency  ").reason == "emergency"


def test_cancel_reason_at_maximum_length_is_accepted():
    assert len(CancelRequest(reason="a" * 500).reason) == 500


@pytest.mark.parametrize("reason", ["", "   ", "a" * 501])
def test_cancel_reason_invalid_values_are_rejected(reason):
    with pytest.raises(ValidationError):
        CancelRequest(reason=reason)


def test_cancel_reason_is_required():
    with pytest.raises(ValidationError):
        CancelRequest()


def test_cancel_request_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        CancelRequest(reason="emergency", token="abc")


# --- RescheduleRequest ------------------------------------------------------


def test_reschedule_accepts_timezone_aware_start():
    request = RescheduleRequest(start_time="2026-11-03T11:00:00+03:00")
    assert request.start_time == datetime(2026, 11, 3, 8, 0, tzinfo=UTC)


@pytest.mark.parametrize("start_time", ["2026-11-03T11:00:00", "not a date"])
def test_reschedule_rejects_invalid_start(start_time):
    with pytest.raises(ValidationError):
        RescheduleRequest(start_time=start_time)


def test_reschedule_start_is_required():
    with pytest.raises(ValidationError):
        RescheduleRequest()


def test_reschedule_cannot_change_doctor():
    # Rescheduling stays with the same doctor, so doctor_id is an unknown field.
    with pytest.raises(ValidationError):
        RescheduleRequest(start_time="2026-11-03T11:00:00+03:00", doctor_id=2)