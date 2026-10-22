"""Seed the clinic's doctors and their weekly working hours.

Run from the repo root (or /code inside the container) with:

    python -m scripts.seed

Idempotent: if any doctor already exists, nothing is inserted, so it is safe
to run on every deploy. The whole seed runs in one transaction, so a failure
part-way leaves the database unchanged.
"""

import asyncio
import logging
from datetime import time

from sqlalchemy import func, select

from clinic_booking_api.database import engine, session_factory
from clinic_booking_api.models import Doctor, WorkingHours

logger = logging.getLogger("seed")

# Weekday convention used across the project: 0 is Monday.
MON, TUE, WED, THU, FRI, SAT = range(6)
MON_TO_FRI = (MON, TUE, WED, THU, FRI)

# Each doctor exercises a different availability rule, so the seeded data
# doubles as a manual demo of the edge cases.
DOCTORS = [
    {
        # Standard full day. Slots 09:00 to 16:30; the 16:30 slot ends exactly
        # at closing time, which the inclusive end boundary allows.
        "first_name": "Elaine",
        "middle_name": None,
        "last_name": "Maina",
        "specialization": "General Practice",
        "hours": [(day, time(9, 0), time(17, 0)) for day in MON_TO_FRI],
    },
    {
        # Hours that start and end off the 30-minute grid. Slots are rounded
        # inward: first slot 10:30, last slot 16:00 (ending 16:30).
        "first_name": "Brian",
        "middle_name": None,
        "last_name": "Otieno",
        "specialization": "Paediatrics",
        "hours": [(day, time(10, 15), time(16, 45)) for day in MON_TO_FRI],
    },
    {
        # Split shift with a lunch break: two windows on the same weekday and
        # no slots between 12:00 and 13:00. Off on Tuesday and Thursday.
        "first_name": "Wanjiru",
        "middle_name": "Njeri",
        "last_name": "Kamau",
        "specialization": "Obstetrics and Gynaecology",
        "hours": [
            *[(day, time(8, 0), time(12, 0)) for day in (MON, WED, FRI)],
            *[(day, time(13, 0), time(17, 0)) for day in (MON, WED, FRI)],
        ],
    },
    {
        # Works Saturday, off on Monday.
        "first_name": "Hassan",
        "middle_name": None,
        "last_name": "Abdi",
        "specialization": "Dermatology",
        "hours": [(day, time(9, 0), time(14, 0)) for day in (TUE, WED, THU, FRI, SAT)],
    },
    {
        # Mid-week day off (Wednesday), and a start on the half hour.
        "first_name": "Grace",
        "middle_name": "Akinyi",
        "last_name": "Achieng",
        "specialization": "Family Medicine",
        "hours": [(day, time(8, 30), time(15, 30)) for day in (MON, TUE, THU, FRI)],
    },
]


async def seed() -> None:
    async with session_factory() as session:
        existing = await session.scalar(select(func.count()).select_from(Doctor))
        if existing:
            logger.info("Found %s doctors already; skipping seed.", existing)
            return

        for spec in DOCTORS:
            doctor = Doctor(
                first_name=spec["first_name"],
                middle_name=spec["middle_name"],
                last_name=spec["last_name"],
                specialization=spec["specialization"],
            )
            session.add(doctor)
            await session.flush()  # sends the insert so doctor.id is assigned

            session.add_all(
                WorkingHours(
                    doctor_id=doctor.id,
                    weekday=day,
                    start_time=start,
                    end_time=end,
                )
                for day, start, end in spec["hours"]
            )

        await session.commit()
        logger.info("Seeded %s doctors with their working hours.", len(DOCTORS))


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    try:
        await seed()
    finally:
        # Close pooled connections so the process exits cleanly.
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
