"""Tests for GET /patients/{id}/appointments.

The listing is unauthenticated by decision, so these tests also prove that
only the minimized fields can appear in it.
"""

import uuid
from datetime import UTC, datetime, time

import pytest
import pytest_asyncio

from clinic_booking_api.dependencies import get_now
from clinic_booking_api.main import app

pytestmark = pytest.mark.asyncio

MONDAY, TUESDAY = 0, 1
LISTING_FIELDS = {"id", "start_time", "end_time", "status", "doctor_id", "doctor_name"}


@pytest_asyncio.fixture
async def doctor(make_doctor):
    return await make_doctor(
        first_name="Elaine",
        last_name="Maina",
        hours=[(MONDAY, time(8), time(17)), (TUESDAY, time(9), time(17))],
    )


async def book(client, doctor_id, start, name="Amina Hassan", phone="0712345678"):
    response = await client.post(
        "/appointments",
        json={
            "doctor_id": doctor_id,
            "start_time": start,
            "name": name,
            "phone": phone,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def listing(client, patient_id):
    return await client.get(f"/patients/{patient_id}/appointments")


async def test_lists_upcoming_appointments_earliest_first(client, doctor, fixed_now):
    later = await book(client, doctor.id, "2026-11-03T11:00:00+03:00")
    earlier = await book(client, doctor.id, "2026-11-03T10:00:00+03:00")

    response = await listing(client, later["patient_id"])

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [earlier["id"], later["id"]]


async def test_items_contain_only_minimized_fields(client, doctor, fixed_now):
    booking = await book(client, doctor.id, "2026-11-03T10:00:00+03:00")

    item = (await listing(client, booking["patient_id"])).json()[0]

    assert set(item) == LISTING_FIELDS
    assert item["doctor_name"] == "Elaine Maina"
    assert item["status"] == "booked"
    assert item["start_time"] == "2026-11-03T10:00:00+03:00"


async def test_cancelled_appointments_are_not_listed(client, doctor, fixed_now):
    kept = await book(client, doctor.id, "2026-11-03T10:00:00+03:00")
    dropped = await book(client, doctor.id, "2026-11-03T11:00:00+03:00")
    await client.patch(
        f"/appointments/{dropped['id']}/cancel",
        json={"reason": "Travelling"},
        headers={"X-Booking-Token": dropped["token"]},
    )

    items = (await listing(client, kept["patient_id"])).json()

    assert [item["id"] for item in items] == [kept["id"]]


async def test_past_appointments_are_not_listed(client, doctor, fixed_now):
    today = await book(client, doctor.id, "2026-11-02T09:00:00+03:00")
    tomorrow = await book(client, doctor.id, "2026-11-03T10:00:00+03:00")
    # Move the clock to 10:00 on Monday, after today's 09:00 appointment.
    app.dependency_overrides[get_now] = lambda: datetime(2026, 11, 2, 7, 0, tzinfo=UTC)

    items = (await listing(client, today["patient_id"])).json()

    assert [item["id"] for item in items] == [tomorrow["id"]]


async def test_other_patients_appointments_are_not_listed(client, doctor, fixed_now):
    mine = await book(client, doctor.id, "2026-11-03T10:00:00+03:00")
    await book(
        client,
        doctor.id,
        "2026-11-03T11:00:00+03:00",
        name="Grace Achieng",
        phone="0722000111",
    )

    items = (await listing(client, mine["patient_id"])).json()

    assert [item["id"] for item in items] == [mine["id"]]


async def test_patient_with_no_upcoming_appointments_gets_an_empty_list(
    client, doctor, fixed_now
):
    booking = await book(client, doctor.id, "2026-11-03T10:00:00+03:00")
    await client.patch(
        f"/appointments/{booking['id']}/cancel",
        json={"reason": "Travelling"},
        headers={"X-Booking-Token": booking["token"]},
    )

    response = await listing(client, booking["patient_id"])

    assert response.status_code == 200
    assert response.json() == []


async def test_unknown_patient_returns_404(client, fixed_now):
    response = await listing(client, uuid.uuid4())

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "patient_not_found"


async def test_malformed_patient_id_returns_422(client, fixed_now):
    response = await listing(client, "not-a-uuid")

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "patient_id"
