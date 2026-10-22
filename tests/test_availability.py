"""Tests for GET /doctors/{id}/availability.

fixed_now freezes the clock at Monday 2 November 2026, 08:00 in Nairobi.
"""

from datetime import date, time
from zoneinfo import ZoneInfo

import pytest

from clinic_booking_api.services.slots import slots_in_window

pytestmark = pytest.mark.asyncio

MONDAY, TUESDAY = 0, 1
TODAY = "2026-11-02"  # Monday; fixed_now is 08:00 on this day
TOMORROW = "2026-11-03"  # Tuesday
DAY_OFF = "2026-11-04"  # Wednesday
LAST_WEEK = "2026-10-26"  # a Monday in the past
NAIROBI = ZoneInfo("Africa/Nairobi")


async def get_slots(client, doctor_id, day):
    return await client.get(f"/doctors/{doctor_id}/availability", params={"date": day})


def starts(response):
    return [slot["start_time"] for slot in response.json()["slots"]]


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


# --- slots_in_window: pure arithmetic, no database --------------------------


async def test_full_day_window_gives_sixteen_slots():
    slots = slots_in_window(date(2026, 11, 3), time(9), time(17), NAIROBI)
    assert len(slots) == 16
    assert (slots[0].hour, slots[0].minute) == (9, 0)
    assert (slots[-1].hour, slots[-1].minute) == (16, 30)  # ends exactly at closing


async def test_off_grid_window_is_rounded_inward():
    slots = slots_in_window(date(2026, 11, 3), time(10, 15), time(16, 45), NAIROBI)
    assert (slots[0].hour, slots[0].minute) == (10, 30)
    assert (slots[-1].hour, slots[-1].minute) == (16, 0)


async def test_window_shorter_than_a_slot_gives_nothing():
    slots = slots_in_window(date(2026, 11, 3), time(10), time(10, 20), NAIROBI)
    assert slots == []


# --- GET /doctors/{id}/availability ---------------------------------------------


async def test_full_day_lists_every_slot_in_clinic_time(client, make_doctor, fixed_now):
    doctor = await make_doctor(hours=[(TUESDAY, time(9), time(17))])

    response = await get_slots(client, doctor.id, TOMORROW)

    assert response.status_code == 200
    body = response.json()
    assert body["doctor_id"] == doctor.id
    assert body["date"] == TOMORROW
    assert body["timezone"] == "Africa/Nairobi"
    assert len(body["slots"]) == 16
    assert body["slots"][0] == {
        "start_time": "2026-11-03T09:00:00+03:00",
        "end_time": "2026-11-03T09:30:00+03:00",
    }
    assert body["slots"][-1]["start_time"] == "2026-11-03T16:30:00+03:00"


async def test_off_grid_working_hours_are_rounded_inward(
    client, make_doctor, fixed_now
):
    doctor = await make_doctor(hours=[(TUESDAY, time(10, 15), time(16, 45))])

    slot_starts = starts(await get_slots(client, doctor.id, TOMORROW))

    assert slot_starts[0] == "2026-11-03T10:30:00+03:00"
    assert slot_starts[-1] == "2026-11-03T16:00:00+03:00"


async def test_split_shift_has_no_slots_during_the_break(
    client, make_doctor, fixed_now
):
    doctor = await make_doctor(
        hours=[(TUESDAY, time(8), time(12)), (TUESDAY, time(13), time(17))]
    )

    slot_starts = starts(await get_slots(client, doctor.id, TOMORROW))

    assert "2026-11-03T11:30:00+03:00" in slot_starts
    assert "2026-11-03T12:00:00+03:00" not in slot_starts
    assert "2026-11-03T12:30:00+03:00" not in slot_starts
    assert "2026-11-03T13:00:00+03:00" in slot_starts


async def test_day_off_returns_an_empty_list(client, make_doctor, fixed_now):
    doctor = await make_doctor(hours=[(TUESDAY, time(9), time(17))])

    response = await get_slots(client, doctor.id, DAY_OFF)

    assert response.status_code == 200
    assert response.json()["slots"] == []


async def test_past_date_returns_an_empty_list(client, make_doctor, fixed_now):
    doctor = await make_doctor(hours=[(MONDAY, time(9), time(17))])

    response = await get_slots(client, doctor.id, LAST_WEEK)

    assert response.status_code == 200
    assert response.json()["slots"] == []


async def test_today_hides_slots_within_one_hour(client, make_doctor, fixed_now):
    # It is 08:00, so 08:00 and 08:30 are too soon; 09:00 is exactly one hour away.
    doctor = await make_doctor(hours=[(MONDAY, time(8), time(17))])

    slot_starts = starts(await get_slots(client, doctor.id, TODAY))

    assert "2026-11-02T08:30:00+03:00" not in slot_starts
    assert slot_starts[0] == "2026-11-02T09:00:00+03:00"


async def test_booked_slot_is_not_available(client, make_doctor, fixed_now):
    doctor = await make_doctor(hours=[(TUESDAY, time(9), time(17))])
    booked = await book(client, doctor.id, "2026-11-03T10:00:00+03:00")
    assert booked.status_code == 201

    slot_starts = starts(await get_slots(client, doctor.id, TOMORROW))

    assert "2026-11-03T10:00:00+03:00" not in slot_starts
    assert len(slot_starts) == 15


async def test_cancelled_slot_becomes_available_again(client, make_doctor, fixed_now):
    doctor = await make_doctor(hours=[(TUESDAY, time(9), time(17))])
    booking = (await book(client, doctor.id, "2026-11-03T10:00:00+03:00")).json()

    cancelled = await client.patch(
        f"/appointments/{booking['id']}/cancel",
        json={"reason": "Travelling"},
        headers={"X-Booking-Token": booking["token"]},
    )
    assert cancelled.status_code == 200

    slot_starts = starts(await get_slots(client, doctor.id, TOMORROW))
    assert "2026-11-03T10:00:00+03:00" in slot_starts


async def test_another_doctors_booking_does_not_affect_availability(
    client, make_doctor, fixed_now
):
    first = await make_doctor(hours=[(TUESDAY, time(9), time(17))])
    second = await make_doctor(first_name="Brian", hours=[(TUESDAY, time(9), time(17))])
    await book(client, first.id, "2026-11-03T10:00:00+03:00")

    slot_starts = starts(await get_slots(client, second.id, TOMORROW))

    assert "2026-11-03T10:00:00+03:00" in slot_starts


async def test_unknown_doctor_returns_404(client, fixed_now):
    response = await get_slots(client, 999, TOMORROW)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "doctor_not_found"


async def test_inactive_doctor_returns_404(client, make_doctor, fixed_now):
    doctor = await make_doctor(is_active=False, hours=[(TUESDAY, time(9), time(17))])

    response = await get_slots(client, doctor.id, TOMORROW)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "doctor_not_found"


async def test_malformed_date_returns_422_naming_the_field(
    client, make_doctor, fixed_now
):
    doctor = await make_doctor()

    response = await get_slots(client, doctor.id, "not-a-date")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["field"] == "date"


async def test_missing_date_returns_422(client, make_doctor, fixed_now):
    doctor = await make_doctor()

    response = await client.get(f"/doctors/{doctor.id}/availability")

    assert response.status_code == 422
