"""Tests for GET /doctors and the doctors service.

Each test starts from empty tables (the client and db_session fixtures clean
the test database first) and creates exactly the doctors it needs.
"""

import pytest

from clinic_booking_api.errors import NotFoundError
from clinic_booking_api.services.doctors import get_active_doctor, list_active_doctors

DOCTOR_OUT_FIELDS = {"id", "first_name", "middle_name", "last_name", "specialization"}


# --- GET /doctors -------------------------------------------------------------


@pytest.mark.asyncio
async def test_lists_only_active_doctors_in_id_order(client, make_doctor):
    first = await make_doctor(first_name="Elaine", last_name="Maina")
    await make_doctor(first_name="Retired", last_name="Doctor", is_active=False)
    third = await make_doctor(first_name="Brian", last_name="Otieno")

    response = await client.get("/doctors")

    assert response.status_code == 200
    body = response.json()
    assert [doctor["id"] for doctor in body] == [first.id, third.id]
    assert [doctor["first_name"] for doctor in body] == ["Elaine", "Brian"]


@pytest.mark.asyncio
async def test_no_doctors_returns_an_empty_list(client):
    response = await client.get("/doctors")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_each_doctor_has_exactly_the_public_fields(client, make_doctor):
    await make_doctor()

    response = await client.get("/doctors")

    doctor = response.json()[0]
    assert set(doctor) == DOCTOR_OUT_FIELDS  # is_active is never exposed


@pytest.mark.asyncio
async def test_middle_name_is_returned_when_present_and_null_when_absent(
    client, make_doctor
):
    await make_doctor(first_name="Wanjiru", middle_name="Njeri", last_name="Kamau")
    await make_doctor(first_name="Hassan", middle_name=None, last_name="Abdi")

    body = (await client.get("/doctors")).json()

    assert body[0]["middle_name"] == "Njeri"
    assert body[1]["middle_name"] is None


@pytest.mark.asyncio
async def test_specialization_is_returned(client, make_doctor):
    await make_doctor(specialization="Paediatrics")

    body = (await client.get("/doctors")).json()

    assert body[0]["specialization"] == "Paediatrics"


# --- Service: list_active_doctors ---------------------------------------------


@pytest.mark.asyncio
async def test_list_active_doctors_returns_a_plain_list(db_session, make_doctor):
    await make_doctor()

    doctors = await list_active_doctors(db_session)

    assert isinstance(doctors, list)
    assert len(doctors) == 1


# --- Service: get_active_doctor -----------------------------------------------


@pytest.mark.asyncio
async def test_get_active_doctor_returns_the_doctor(db_session, make_doctor):
    created = await make_doctor(first_name="Grace")

    doctor = await get_active_doctor(db_session, created.id)

    assert doctor.id == created.id
    assert doctor.first_name == "Grace"


@pytest.mark.asyncio
async def test_get_active_doctor_missing_id_raises_not_found(db_session):
    with pytest.raises(NotFoundError) as exc_info:
        await get_active_doctor(db_session, 999)

    assert exc_info.value.code == "doctor_not_found"


@pytest.mark.asyncio
async def test_get_active_doctor_inactive_raises_not_found(db_session, make_doctor):
    # A doctor who has left gets the same 404 as one who never existed.
    retired = await make_doctor(is_active=False)

    with pytest.raises(NotFoundError) as exc_info:
        await get_active_doctor(db_session, retired.id)

    assert exc_info.value.code == "doctor_not_found"
