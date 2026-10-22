"""Tests for the error classes and exception handlers.

These use a tiny app built only for this file, with the same handlers as the
real app, so test-only routes never leak into the real API. No database is used.
"""

from typing import Annotated

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import AfterValidator, BaseModel, ConfigDict

from clinic_booking_api.errors import (
    AppError,
    BookingRuleError,
    ConflictError,
    NotFoundError,
    register_exception_handlers,
)
from clinic_booking_api.services.normalization import normalize_phone

test_app = FastAPI()
register_exception_handlers(test_app)


class PhoneBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: Annotated[str, AfterValidator(normalize_phone)]


@test_app.get("/not-found")
async def raise_not_found():
    raise NotFoundError("doctor_not_found", "Doctor not found.")


@test_app.get("/conflict")
async def raise_conflict():
    raise ConflictError(
        "slot_taken", "This booking conflicts with an existing booking."
    )


@test_app.get("/rule")
async def raise_rule():
    raise BookingRuleError("too_soon", "Bookings must start at least 1 hour from now.")


@test_app.get("/unclassified")
async def raise_plain_app_error():
    raise AppError("unclassified", "Something went wrong.")


@test_app.get("/bug")
async def raise_unexpected_bug():
    raise KeyError("a genuine bug, not an API error")


@test_app.post("/phone")
async def check_phone(body: PhoneBody):
    return {"phone": body.phone}


@test_app.get("/items")
async def list_items(limit: int):
    return {"limit": limit}


@pytest_asyncio.fixture
async def error_client():
    # raise_app_exceptions=False lets the unexpected-bug test see the 500
    # response instead of the exception escaping into the test.
    transport = ASGITransport(app=test_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# --- AppError and its subclasses --------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/not-found", 404, "doctor_not_found"),
        ("/conflict", 409, "slot_taken"),
        ("/rule", 422, "too_soon"),
        ("/unclassified", 500, "unclassified"),
    ],
)
async def test_app_errors_use_the_standard_shape(error_client, path, status, code):
    response = await error_client.get(path)

    assert response.status_code == status
    error = response.json()["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str)
    assert error["message"]
    assert error["details"] is None


@pytest.mark.asyncio
async def test_unexpected_bugs_are_not_dressed_up_as_api_errors(error_client):
    # A genuine bug has no handler of ours, so it stays a plain 500.
    response = await error_client.get("/bug")

    assert response.status_code == 500
    # Starlette's default plain-text response, not our JSON error shape.
    assert response.text == "Internal Server Error"


# --- Validation errors ------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_body_field_uses_the_standard_shape(error_client):
    response = await error_client.post("/phone", json={"phone": "abc"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["message"]
    assert len(error["details"]) == 1
    detail = error["details"][0]
    assert detail["field"] == "phone"
    # Pydantic's prefix is removed, so the client sees just our sentence.
    assert not detail["message"].startswith("Value error")
    assert detail["message"].startswith("Phone must")


@pytest.mark.asyncio
async def test_missing_field_is_reported(error_client):
    response = await error_client.post("/phone", json={})

    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert [detail["field"] for detail in details] == ["phone"]


@pytest.mark.asyncio
async def test_unknown_field_is_reported(error_client):
    response = await error_client.post(
        "/phone", json={"phone": "0712345678", "extra": "not allowed"}
    )

    assert response.status_code == 422
    fields = [detail["field"] for detail in response.json()["error"]["details"]]
    assert "extra" in fields


@pytest.mark.asyncio
async def test_query_parameter_error_names_the_parameter(error_client):
    # loc is ("query", "limit"); the "query" part is dropped.
    response = await error_client.get("/items", params={"limit": "abc"})

    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert details[0]["field"] == "limit"


@pytest.mark.asyncio
async def test_valid_body_still_works(error_client):
    response = await error_client.post("/phone", json={"phone": "0712 345 678"})

    assert response.status_code == 200
    assert response.json() == {"phone": "+254712345678"}
