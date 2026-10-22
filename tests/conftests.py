"""Shared test setup.

Tests run against a separate database (TEST_DATABASE_URL), never the
development or production one, because the cleaning fixture empties tables.

The environment is set up at the very top of this file, before any import from
the app: the app reads DATABASE_URL when database.py is first imported, and
pytest loads conftest.py before any test module.
"""

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from urllib.parse import urlparse

import pytest
from dotenv import load_dotenv

from clinic_booking_api.dependencies import get_now

load_dotenv()  # copies .env into the environment without overwriting existing values

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError(
        "TEST_DATABASE_URL is not set. Add it to .env or the CI environment."
    )

# Safety lock: the cleaning fixture empties tables, so never run against a
# database whose name doesn't say it's for tests.
if "test" not in urlparse(TEST_DATABASE_URL).path:
    raise RuntimeError(
        "Refusing to run tests: TEST_DATABASE_URL must point at a test database "
        f"(got database {urlparse(TEST_DATABASE_URL).path!r})."
    )

# Point the whole app at the test database. Environment variables take
# priority over .env, so get_settings() now returns this URL.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

# App imports must come after the environment is set up, hence the noqa markers.
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from datetime import time

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from clinic_booking_api.config import get_settings
from clinic_booking_api.database import get_db
from clinic_booking_api.main import app
from clinic_booking_api.models import Doctor, WorkingHours

# NullPool opens a fresh connection for each use and closes it afterwards.
# pytest-asyncio gives each test its own event loop, and a pooled connection
# created in one test's loop fails when reused in the next test's loop.
test_engine = create_async_engine(str(get_settings().database_url), poolclass=NullPool)
TestSessionFactory = async_sessionmaker(test_engine, expire_on_commit=False)


async def override_get_db() -> AsyncIterator[AsyncSession]:
    async with TestSessionFactory() as session:
        yield session


# Every request the app handles during tests uses the test engine.
app.dependency_overrides[get_db] = override_get_db

TABLES = "appointments, patients, working_hours, doctors"


@pytest_asyncio.fixture
async def clean_database() -> AsyncIterator[None]:
    """Empty every table before the test, so each test starts from nothing.

    RESTART IDENTITY resets the doctor id counter, so the first doctor a test
    creates is always id 1.
    """
    async with test_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    yield


@pytest_asyncio.fixture
async def db_session(clean_database) -> AsyncIterator[AsyncSession]:
    """A session for arranging test data directly in the database."""
    async with TestSessionFactory() as session:
        yield session


@pytest_asyncio.fixture
async def client(clean_database) -> AsyncIterator[AsyncClient]:
    """An HTTP client that calls the app in memory, with no server running."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


WorkingWindow = tuple[int, time, time]  # (weekday, start, end); 0 is Monday


@pytest_asyncio.fixture
async def make_doctor(db_session) -> Callable[..., Awaitable[Doctor]]:
    """Create a doctor (and optional working hours) in one line.

    Example:
        doctor = await make_doctor(hours=[(0, time(9), time(17))])
    """

    async def _make_doctor(
        *,
        first_name: str = "Test",
        middle_name: str | None = None,
        last_name: str = "Doctor",
        specialization: str = "General Practice",
        is_active: bool = True,
        hours: Iterable[WorkingWindow] = (),
    ) -> Doctor:
        doctor = Doctor(
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            specialization=specialization,
            is_active=is_active,
        )
        db_session.add(doctor)
        await db_session.flush()  # assigns doctor.id

        db_session.add_all(
            WorkingHours(
                doctor_id=doctor.id, weekday=weekday, start_time=start, end_time=end
            )
            for weekday, start, end in hours
        )
        # Commit, because the app reads through its own session and only sees
        # committed rows.
        await db_session.commit()
        return doctor

    return _make_doctor


FIXED_NOW = datetime(2026, 11, 2, 5, 0, tzinfo=UTC)  # Monday 08:00 in Nairobi


@pytest.fixture
def fixed_now() -> Iterator[datetime]:
    """Freeze the app's clock at FIXED_NOW for one test."""
    app.dependency_overrides[get_now] = lambda: FIXED_NOW
    yield FIXED_NOW
    app.dependency_overrides.pop(get_now, None)
