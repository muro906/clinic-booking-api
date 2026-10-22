"""Tests for booking, cancelling and rescheduling.

fixed_now freezes the clock at Monday 2 November 2026, 08:00 in Nairobi
(05:00 UTC). Most bookings use Tuesday 3 November, safely in the future.
"""

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime, time

import pytest
import pytest_asyncio
from sqlalchemy import select

from clinic_booking_api.dependencies import get_now
from clinic_booking_api.main import app
from clinic_booking_api.models import Appointment

pytestmark = pytest.mark.asyncio

MONDAY, TUESDAY = 0, 1
TUESDAY_10 = "2026-11-03T10:00:00+03:00"
TUESDAY_10_30 = "2026-11-03T10:30:00+03:00"
TUESDAY_11 = "2026-11-03T11:00:00+03:00"


@pytest_asyncio.fixture
async def doctor(make_doctor):
    """Works Monday 08:00 to 17:00 and Tuesday 09:00 to 17:00."""
    return await make_doctor(
        first_name="Elaine",
        last_name="Maina",
        hours=[(MONDAY, time(8), time(17)), (TUESDAY, time(9), time(17))],
    )


@pytest_asyncio.fixture
async def second_doctor(make_doctor):
    return await make_doctor(
        first_name="Brian", last_name="Otieno", hours=[(TUESDAY, time(9), time(17))]
    )


def set_now(moment: datetime) -> None:
    """Move the frozen clock. fixed_now removes the override after the test."""
    app.dependency_overrides[get_now] = lambda: moment


async def book(client, doctor_id, start, name="Amina Hassan", phone="0712345678"):
    return await client.post(
        "/appointments",
        json={
            "doctor_id": doctor_id,
            "start_time": start,
            "name": name,
            "phone": phone,
        },
    )


async def cancel(client, appointment_id, token, reason="Travelling"):
    return await client.patch(
        f"/appointments/{appointment_id}/cancel",
        json={"reason": reason},
        headers={"X-Booking-Token": token},
    )


async def reschedule(client, appointment_id, token, start):
    return await client.patch(
        f"/appointments/{appointment_id}/reschedule",
        json={"start_time": start},
        headers={"X-Booking-Token": token},
    )


def error_code(response):
    return response.json()["error"]["code"]


# --- POST /appointments: success --------------------------------------------------


async def test_booking_returns_201_with_token_once(client, doctor, fixed_now):
    response = await book(client, doctor.id, TUESDAY_10)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "booked"
    assert body["doctor_id"] == doctor.id
    assert body["start_time"] == TUESDAY_10
    assert body["end_time"] == TUESDAY_10_30
    assert body["token"]
    assert "token_hash" not in body
    assert body["cancel_reason"] is None


async def test_only_the_token_hash_is_stored(client, doctor, db_session, fixed_now):
    body = (await book(client, doctor.id, TUESDAY_10)).json()

    stored = await db_session.scalar(
        select(Appointment.token_hash).where(Appointment.id == uuid.UUID(body["id"]))
    )

    assert stored != body["token"]
    assert stored == hashlib.sha256(body["token"].encode()).hexdigest()


async def test_utc_input_is_accepted_and_returned_in_clinic_time(
    client, doctor, fixed_now
):
    response = await book(client, doctor.id, "2026-11-03T07:00:00Z")  # 10:00 in Nairobi

    assert response.status_code == 201
    assert response.json()["start_time"] == TUESDAY_10


async def test_booking_exactly_one_hour_ahead_is_allowed(client, doctor, fixed_now):
    response = await book(client, doctor.id, "2026-11-02T09:00:00+03:00")

    assert response.status_code == 201


async def test_same_person_reuses_one_patient_record(client, doctor, fixed_now):
    first = (await book(client, doctor.id, TUESDAY_10)).json()
    second = (
        await book(client, doctor.id, TUESDAY_11, phone="+254 712 345 678")
    ).json()

    assert first["patient_id"] == second["patient_id"]


# --- POST /appointments: rule violations (422) ----------------------------------


@pytest.mark.parametrize(
    ("start", "code"),
    [
        ("2026-11-03T10:15:00+03:00", "off_grid"),
        ("2026-11-02T07:00:00+03:00", "in_the_past"),
        ("2026-11-02T08:30:00+03:00", "too_soon"),
        ("2026-11-03T08:30:00+03:00", "outside_working_hours"),  # before opening
        ("2026-11-03T16:45:00+03:00", "off_grid"),
        ("2026-11-03T17:00:00+03:00", "outside_working_hours"),  # would end at 17:30
        ("2026-11-04T10:00:00+03:00", "outside_working_hours"),  # Wednesday, day off
    ],
)
async def test_booking_rule_violations_return_422(
    client, doctor, fixed_now, start, code
):
    response = await book(client, doctor.id, start)

    assert response.status_code == 422
    assert error_code(response) == code


async def test_booking_without_timezone_is_rejected(client, doctor, fixed_now):
    response = await book(client, doctor.id, "2026-11-03T10:00:00")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["field"] == "start_time"


async def test_unknown_doctor_returns_404(client, fixed_now):
    response = await book(client, 999, TUESDAY_10)

    assert response.status_code == 404
    assert error_code(response) == "doctor_not_found"


async def test_inactive_doctor_returns_404(client, make_doctor, fixed_now):
    retired = await make_doctor(is_active=False, hours=[(TUESDAY, time(9), time(17))])

    response = await book(client, retired.id, TUESDAY_10)

    assert response.status_code == 404
    assert error_code(response) == "doctor_not_found"


# --- POST /appointments: conflicts (409) -----------------------------------------


async def test_taken_slot_returns_409(client, doctor, fixed_now):
    await book(client, doctor.id, TUESDAY_10)

    response = await book(
        client, doctor.id, TUESDAY_10, name="Grace Achieng", phone="0722000111"
    )

    assert response.status_code == 409
    assert error_code(response) == "booking_conflict"


async def test_same_person_cannot_hold_two_doctors_at_once(
    client, doctor, second_doctor, fixed_now
):
    await book(client, doctor.id, TUESDAY_10)

    # Same person, written differently: casing, spacing and phone format.
    response = await book(
        client,
        second_doctor.id,
        TUESDAY_10,
        name="  AMINA   hassan ",
        phone="+254 712 345 678",
    )

    assert response.status_code == 409
    assert error_code(response) == "booking_conflict"


async def test_family_member_on_the_same_phone_can_book_the_same_time(
    client, doctor, second_doctor, fixed_now
):
    await book(client, doctor.id, TUESDAY_10)

    response = await book(client, second_doctor.id, TUESDAY_10, name="Yusuf Hassan")

    assert response.status_code == 201


async def test_simultaneous_bookings_for_one_slot_produce_exactly_one_success(
    client, doctor, fixed_now
):
    people = [
        ("Patient Alpha", "0712000001"),
        ("Patient Bravo", "0712000002"),
        ("Patient Charlie", "0712000003"),
        ("Patient Delta", "0712000004"),
        ("Patient Echo", "0712000005"),
    ]

    responses = await asyncio.gather(
        *(
            book(client, doctor.id, TUESDAY_10, name=name, phone=phone)
            for name, phone in people
        )
    )

    assert sorted(response.status_code for response in responses) == [
        201,
        409,
        409,
        409,
        409,
    ]


# --- PATCH /appointments/{id}/cancel ---------------------------------------------


async def test_cancel_records_reason_and_time(client, doctor, fixed_now):
    booking = (await book(client, doctor.id, TUESDAY_10)).json()

    response = await cancel(
        client, booking["id"], booking["token"], reason="  Travelling  "
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["cancel_reason"] == "Travelling"
    assert body["cancelled_at"] == "2026-11-02T08:00:00+03:00"
    assert "token" not in body


async def test_cancel_frees_the_slot_for_someone_else(client, doctor, fixed_now):
    booking = (await book(client, doctor.id, TUESDAY_10)).json()
    await cancel(client, booking["id"], booking["token"])

    response = await book(
        client, doctor.id, TUESDAY_10, name="Grace Achieng", phone="0722000111"
    )

    assert response.status_code == 201


async def test_cancel_twice_returns_409(client, doctor, fixed_now):
    booking = (await book(client, doctor.id, TUESDAY_10)).json()
    await cancel(client, booking["id"], booking["token"])

    response = await cancel(client, booking["id"], booking["token"])

    assert response.status_code == 409
    assert error_code(response) == "already_cancelled"


async def test_wrong_token_and_unknown_id_give_the_same_404(client, doctor, fixed_now):
    booking = (await book(client, doctor.id, TUESDAY_10)).json()

    wrong_token = await cancel(client, booking["id"], "not-the-token")
    unknown_id = await cancel(client, str(uuid.uuid4()), booking["token"])

    assert wrong_token.status_code == unknown_id.status_code == 404
    assert wrong_token.json() == unknown_id.json()
    assert error_code(wrong_token) == "appointment_not_found"


async def test_one_appointments_token_cannot_cancel_another(client, doctor, fixed_now):
    first = (await book(client, doctor.id, TUESDAY_10)).json()
    second = (await book(client, doctor.id, TUESDAY_11)).json()

    response = await cancel(client, second["id"], first["token"])

    assert response.status_code == 404


async def test_cancel_without_token_header_returns_422(client, doctor, fixed_now):
    booking = (await book(client, doctor.id, TUESDAY_10)).json()

    response = await client.patch(
        f"/appointments/{booking['id']}/cancel", json={"reason": "Travelling"}
    )

    assert response.status_code == 422


async def test_cancel_requires_a_reason(client, doctor, fixed_now):
    booking = (await book(client, doctor.id, TUESDAY_10)).json()

    response = await cancel(client, booking["id"], booking["token"], reason="   ")

    assert response.status_code == 422


async def test_cannot_cancel_an_appointment_that_has_started(client, doctor, fixed_now):
    booking = (await book(client, doctor.id, "2026-11-02T09:00:00+03:00")).json()
    set_now(datetime(2026, 11, 2, 6, 10, tzinfo=UTC))  # 09:10 in Nairobi

    response = await cancel(client, booking["id"], booking["token"])

    assert response.status_code == 422
    assert error_code(response) == "already_started"


# --- PATCH /appointments/{id}/reschedule ------------------------------------------


async def test_reschedule_moves_the_appointment_and_frees_the_old_slot(
    client, doctor, fixed_now
):
    booking = (await book(client, doctor.id, TUESDAY_10)).json()

    response = await reschedule(client, booking["id"], booking["token"], TUESDAY_11)

    assert response.status_code == 200
    assert response.json()["start_time"] == TUESDAY_11
    availability = await client.get(
        f"/doctors/{doctor.id}/availability", params={"date": "2026-11-03"}
    )
    slot_starts = [slot["start_time"] for slot in availability.json()["slots"]]
    assert TUESDAY_10 in slot_starts
    assert TUESDAY_11 not in slot_starts


async def test_reschedule_onto_a_taken_slot_returns_409_and_keeps_the_original(
    client, doctor, fixed_now
):
    mine = (await book(client, doctor.id, TUESDAY_10)).json()
    await book(client, doctor.id, TUESDAY_11, name="Grace Achieng", phone="0722000111")

    response = await reschedule(client, mine["id"], mine["token"], TUESDAY_11)

    assert response.status_code == 409
    assert error_code(response) == "booking_conflict"
    listing = await client.get(f"/patients/{mine['patient_id']}/appointments")
    assert [item["start_time"] for item in listing.json()] == [TUESDAY_10]


async def test_reschedule_into_a_cancelled_slot_succeeds(client, doctor, fixed_now):
    other = (
        await book(
            client, doctor.id, TUESDAY_11, name="Grace Achieng", phone="0722000111"
        )
    ).json()
    await cancel(client, other["id"], other["token"])
    mine = (await book(client, doctor.id, TUESDAY_10)).json()

    response = await reschedule(client, mine["id"], mine["token"], TUESDAY_11)

    assert response.status_code == 200


async def test_cancelled_appointment_cannot_be_rescheduled(client, doctor, fixed_now):
    booking = (await book(client, doctor.id, TUESDAY_10)).json()
    await cancel(client, booking["id"], booking["token"])

    response = await reschedule(client, booking["id"], booking["token"], TUESDAY_11)

    assert response.status_code == 409
    assert error_code(response) == "appointment_cancelled"


async def test_reschedule_to_the_same_time_is_rejected(client, doctor, fixed_now):
    booking = (await book(client, doctor.id, TUESDAY_10)).json()

    response = await reschedule(client, booking["id"], booking["token"], TUESDAY_10)

    assert response.status_code == 422
    assert error_code(response) == "same_slot"


@pytest.mark.parametrize(
    ("start", "code"),
    [
        ("2026-11-03T11:15:00+03:00", "off_grid"),
        ("2026-11-02T08:30:00+03:00", "too_soon"),
        ("2026-11-03T18:00:00+03:00", "outside_working_hours"),
    ],
)
async def test_reschedule_validates_like_a_fresh_booking(
    client, doctor, fixed_now, start, code
):
    booking = (await book(client, doctor.id, TUESDAY_10)).json()

    response = await reschedule(client, booking["id"], booking["token"], start)

    assert response.status_code == 422
    assert error_code(response) == code


async def test_reschedule_cannot_change_the_doctor(
    client, doctor, second_doctor, fixed_now
):
    booking = (await book(client, doctor.id, TUESDAY_10)).json()

    response = await client.patch(
        f"/appointments/{booking['id']}/reschedule",
        json={"start_time": TUESDAY_11, "doctor_id": second_doctor.id},
        headers={"X-Booking-Token": booking["token"]},
    )

    assert response.status_code == 422
    assert error_code(response) == "validation_error"


async def test_reschedule_with_wrong_token_returns_404(client, doctor, fixed_now):
    booking = (await book(client, doctor.id, TUESDAY_10)).json()

    response = await reschedule(client, booking["id"], "not-the-token", TUESDAY_11)

    assert response.status_code == 404
    assert error_code(response) == "appointment_not_found"
