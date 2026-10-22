# Clinic Booking API

A REST API for a small clinic with five doctors. Patients see a doctor's free
30-minute slots for a day, book one, and can cancel or reschedule it. Built with
FastAPI (async), SQLAlchemy 2.0, PostgreSQL and Alembic, deployed on Render with
a GitHub Actions pipeline.

## Links

- **Live API:** https://clinic-booking-api-hvrp.onrender.com
- **Interactive docs:** https://clinic-booking-api-hvrp.onrender.com/docs
- **Health check:** https://clinic-booking-api-hvrp.onrender.com/health
- **Repository:** https://github.com/muro906/clinic-booking-api

> The service runs on Render's free tier and sleeps after about 15 minutes
> without traffic. The first request after a pause can take up to a minute.

## Try it

The easiest way is the `/docs` page. With curl:

```bash
BASE=https://clinic-booking-api-hvrp.onrender.com

# 1. List doctors and pick an id
curl $BASE/doctors

# 2. Free slots for doctor 1 on a date (YYYY-MM-DD)
curl "$BASE/doctors/1/availability?date=2026-11-03"

# 3. Book a slot. The response includes a token, shown only once: keep it.
curl -X POST $BASE/appointments -H "Content-Type: application/json" -d '{
  "doctor_id": 1,
  "start_time": "2026-11-03T10:00:00+03:00",
  "name": "Amina Hassan",
  "phone": "0712345678"
}'

# 4. Reschedule with the token
curl -X PATCH $BASE/appointments/<APPOINTMENT_ID>/reschedule \
  -H "Content-Type: application/json" -H "X-Booking-Token: <TOKEN>" \
  -d '{"start_time": "2026-11-03T11:00:00+03:00"}'

# 5. Cancel with a reason
curl -X PATCH $BASE/appointments/<APPOINTMENT_ID>/cancel \
  -H "Content-Type: application/json" -H "X-Booking-Token: <TOKEN>" \
  -d '{"reason": "Travelling"}'

# 6. A patient's upcoming appointments (patient_id comes from the booking response)
curl $BASE/patients/<PATIENT_ID>/appointments
```

The database is seeded with five doctors whose schedules exercise the edge cases:
standard hours, hours that start off the half hour (10:15), a split shift with a
lunch break, Saturday work, and a mid-week day off.

---

## Section 1: System design

### Scope and assumptions

- One clinic, timezone Africa/Nairobi (UTC+3, no daylight saving).
- Every appointment is exactly one 30-minute slot.
- Patients book online without an account. Full patient registration happens at
  the clinic, which is how most Kenyan clinics work today.
- Doctors and their working hours are seeded, not managed through the API.

### Components

```mermaid
flowchart LR
    Client[Client or /docs] --> API[FastAPI app<br/>routers, services, schemas]
    API --> DB[(PostgreSQL)]
    GH[GitHub Actions] -->|tests pass, deploy hook| Render[Render web service]
    Render --- API
```

- **Routers** handle HTTP only: parsing, status codes, dependencies.
- **Services** hold the business rules: availability, booking, cancel, reschedule.
- **Schemas** (Pydantic) define what clients may send and what they get back.
- **Models** (SQLAlchemy) define the tables, constraints and indexes.
- **Migrations** (Alembic) build the schema; a seed script adds the doctors.

### Data model

```mermaid
erDiagram
    DOCTORS ||--o{ WORKING_HOURS : "has"
    DOCTORS ||--o{ APPOINTMENTS : "sees"
    PATIENTS ||--o{ APPOINTMENTS : "books"

    DOCTORS {
        int id PK
        text first_name
        text middle_name "nullable"
        text last_name
        text specialization
        boolean is_active
    }
    WORKING_HOURS {
        int id PK
        int doctor_id FK
        smallint weekday "0 = Monday"
        time start_time
        time end_time
    }
    PATIENTS {
        uuid id PK
        text name
        text name_normalized
        text phone_e164
        text email "nullable"
        timestamptz created_at
    }
    APPOINTMENTS {
        uuid id PK
        int doctor_id FK
        uuid patient_id FK
        timestamptz start_time
        timestamptz end_time
        text status "booked or cancelled"
        text cancel_reason "nullable"
        timestamptz cancelled_at "nullable"
        text token_hash
        timestamptz created_at
    }
```

- **doctors:** deactivated with `is_active` rather than deleted, so past
  appointments still point at a real row.
- **working_hours:** repeating weekly clock times. Several rows per weekday are
  allowed, for breaks and split shifts.
- **patients:** a minimal contact record, one row per person as the clinic knows
  them, unique on (normalized phone, normalized name).
- **appointments:** links doctors and patients (many-to-many). It is more than a
  plain junction table: it has its own identity, its own data, and the same
  doctor and patient can appear together many times. Cancelled rows are kept.

### Where each rule is enforced

Rules that must hold even when two requests arrive at the same moment are
enforced by PostgreSQL. A check-then-insert in application code is not safe,
because both requests can pass the check. The API attempts the write and the
database rejects the loser, which the API returns as a 409.

| Rule | Enforced by |
| --- | --- |
| No double booking of a doctor's slot | Partial unique index `uq_doctor_slot_booked` on (doctor_id, start_time) WHERE status = 'booked' |
| One person cannot hold two bookings at the same time | Partial unique index `uq_patient_slot_booked` on (patient_id, start_time) WHERE status = 'booked' |
| Every appointment is exactly 30 minutes | CHECK `ck_slot_duration` |
| Appointments start on the 30-minute grid | CHECK `ck_slot_aligned` (epoch seconds divisible by 1800; valid because UTC+3 is a whole number of half-hours) |
| Status is booked or cancelled | CHECK `ck_status` |
| A cancelled appointment has a reason and a timestamp | CHECK `ck_cancel_fields` |
| One patient row per phone and normalized name | Unique constraint `uq_patient_contact` |

**Why the unique indexes are partial:** they only count rows that are currently
booked. Cancelling changes the status, which removes the row from the index and
frees the slot, while the cancelled row stays for history.

Rules that depend on the current time or on other tables cannot be CHECK
constraints, so the service validates them before writing:

1. The start is on the grid (:00 or :30, clinic time).
2. It is not in the past.
3. It is at least 1 hour away, so the doctor has time to prepare (exactly 1 hour is allowed).
4. The doctor exists and is active.
5. The slot lies entirely inside one of the doctor's working windows for that weekday.

### Indexes

| Index | Table | Partial? | Serves |
| --- | --- | --- | --- |
| Primary keys | all four | No | Lookups by id |
| `ix_working_hours_doctor_weekday` | working_hours | No | A doctor's windows for one weekday |
| `uq_patient_contact` | patients | No | Finding an existing patient at booking |
| `uq_doctor_slot_booked` | appointments | Yes | Double-booking guard and the availability query |
| `uq_patient_slot_booked` | appointments | Yes | Same-person guard and the patient listing |

Queries that should use the partial indexes include `status = 'booked'`.

### Key decisions and trade-offs

| Decision | Choice | Why | Rejected alternative |
| --- | --- | --- | --- |
| Double-booking guard | Partial unique index | The database decides under concurrency; cancelled rows free their slot | A composite key including the patient (does not stop two patients taking one slot); an application check alone (races) |
| Slots | Computed at request time | No slots table to keep in sync with working hours | Stored slot rows, which need a generation job and drift when hours change |
| Grid and working hours | One global 30-minute grid; working hours may start at any minute, and edge minutes go unused | The grid is enforceable in a single-table CHECK | Restricting hours to :00/:30; per-doctor grids the database cannot enforce |
| Cancel | Status change with reason and timestamp | Keeps history for audits and disputes | Hard delete |
| Time | Store UTC (`timestamptz`), interpret working hours in clinic time, return clinic time with offset | No ambiguity at day boundaries | Local times everywhere |
| Keys | UUIDs for patients and appointments, integers for doctors | Ids in URLs cannot be guessed; doctor ids are easy to type | Sequential ids everywhere |
| Reschedule | Same doctor only, one transaction | Simplest rule matching the brief; a failed move leaves the original untouched | Moving across doctors (growth) |
| Concurrency model | Async end to end (FastAPI, AsyncSession, asyncpg) | Request load matters early, whatever the number of doctors | Sync with a threadpool, scaled by adding instances |

### Patient identity: guest booking with a token

Patients book without an account, the way airlines handle bookings: a booking
reference instead of a login.

- Booking captures only a name and phone, with email optional.
- The API returns a random secret token once (256 bits, from `secrets.token_urlsafe`).
  Only its SHA-256 hash is stored, so a database leak exposes no usable tokens.
- Cancel and reschedule require the token in the `X-Booking-Token` header, never
  in the URL, because URLs end up in logs.
- A wrong token and an unknown appointment return the same 404, so ids cannot be probed.

**Why:** the clinic should not hold data for people who may never attend,
clinics capture details at arrival, and reviewers can test the API without
credentials. **Rejected:** full accounts (register, login, password hashing),
which add endpoints outside the brief and a login barrier.

**Known limitations:** possession of the token is the only proof of ownership,
a lost token cannot be recovered through the API, and contact details are unverified.

### Input normalization

**Names:** Unicode-normalized (NFKC) and casefolded; curly apostrophes mapped to
straight; punctuation removed except hyphens and apostrophes; whitespace trimmed
and collapsed. Names containing digits or underscores are rejected rather than
silently changed. Accents are kept ("José" and "Jose" may be different people).
Spaces inside a name are kept as word boundaries, so "Am i n a" is a different
name from "Amina"; removing all spaces would merge distinct names such as
"Ann Marie" and "Anna Rie".

**Phones:** parsed with the `phonenumbers` library (default region Kenya) and
stored as E.164. `0712345678`, `712345678`, `+254712345678`, `254712345678`,
`000254712345678`, `+254 0712 345 678`, and spaced, dashed or bracketed versions
all resolve to `+254712345678`. Only Kenyan numbers are accepted.

**Limitation:** validation checks format, not existence. A well-formed number
that belongs to nobody, or to someone else, is accepted. The contact key
therefore prevents accidental duplicate bookings; it is not proof of identity.

### Overlapping bookings by the same person

The same person (same normalized phone and name) cannot hold two booked
appointments at the same time, with any doctor. A family member sharing a phone
but with a different name can. Conflicts return one generic 409 that does not
say which rule fired, so the API never reveals whether a number has a booking.

Rejected: a phone-only rule (blocks families, lets anyone block a number); fuzzy
name matching (cannot be indexed); collecting date of birth or ID numbers
(contradicts data minimization).

### Patient appointments listing (bonus)

`GET /patients/{id}/appointments` returns upcoming booked appointments, earliest
first, with only the appointment id, times, status and doctor. Never contact
details, the token, or a cancel reason.

**Known weakness, accepted for a bonus endpoint:** anyone who books with another
person's exact phone and name reuses that patient record, receives its id, and
can list that person's upcoming appointments. Growth path: a patient-level secret
issued once, or one-time-code verification of the phone.

### Caching: designed, not built

At five doctors, availability is a small indexed lookup, so no cache is built.
The first scaling step would be caching booked start times per doctor per day
(computing free slots on each request, since "too soon" depends on the current
time), invalidated on book, cancel and reschedule, with a 1 to 5 minute expiry
as a safety net. Writes never read the cache; the unique indexes stay the source
of truth. It would start in memory and move to Redis once more than one instance runs.

### Ambiguities and the decisions made

- **Booking an account?** No: guest booking with a token (above).
- **How a client finds doctor ids:** an added `GET /doctors` endpoint, since the
  brief's booking endpoint needs a doctor id and nothing else provides one.
- **Working hours at odd minutes:** allowed; slots are rounded inward.
- **A slot ending exactly at closing time:** valid.
- **Same person, two doctors, same time:** blocked; family members on one phone allowed.
- **Rescheduling:** same doctor only; moving to the same time is rejected.
- **Cancellation cutoff:** none, except an appointment that has started cannot be cancelled.
- **Availability for a past date or day off:** 200 with an empty list.
- **Unknown fields in requests:** rejected with 422 (`extra="forbid"`), so a typo
  is never silently ignored.

### Growth notes

- **50 doctors:** nothing changes; measure query latency first.
- **500 doctors or several clinics:** add a clinic id, cache availability, move
  to several app instances (the app is stateless), add read replicas for availability.
- **Variable appointment lengths:** replace the grid CHECK with an exclusion
  constraint on a `tstzrange`.
- **Verified identity:** one-time SMS codes, then enforce on the verified phone alone.
- **Notifications:** confirmation SMS or email sent after the response, through a queue.
- Doctor time off, `effective_from` and `effective_to` on working hours, and a
  specializations table.

### Known limitations

- Overlapping working-hours rows for one doctor are not blocked.
- The seed script's "skip if doctors exist" check is not safe if two instances
  start at the same moment; with one instance on Render it cannot happen.
- See also the token, listing and phone-validation limitations above.

---

## Section 2: API

| Method | Path | Purpose | Success |
| --- | --- | --- | --- |
| GET | `/health` | Database connectivity check | 200, or 503 if the database is unreachable |
| GET | `/doctors` | Active doctors | 200 |
| GET | `/doctors/{id}/availability?date=YYYY-MM-DD` | Free 30-minute slots for a day | 200 |
| POST | `/appointments` | Book a slot; returns the token once | 201 |
| PATCH | `/appointments/{id}/cancel` | Cancel with a reason (token header) | 200 |
| PATCH | `/appointments/{id}/reschedule` | Move to a new slot, same doctor (token header) | 200 |
| GET | `/patients/{id}/appointments` | Upcoming booked appointments | 200 |

All response times are in the clinic's timezone with an explicit offset, for
example `2026-11-03T10:00:00+03:00`. Request times must include a timezone.

### Errors

Every error uses one shape:

```json
{
  "error": {
    "code": "booking_conflict",
    "message": "This booking conflicts with an existing booking.",
    "details": null
  }
}
```

For validation errors, `details` lists each bad field and its message.

| Status | Codes |
| --- | --- |
| 404 | `doctor_not_found`, `appointment_not_found`, `patient_not_found` |
| 409 | `booking_conflict`, `already_cancelled`, `appointment_cancelled` |
| 422 | `validation_error`, `off_grid`, `in_the_past`, `too_soon`, `outside_working_hours`, `same_slot`, `already_started`, `invalid_slot` |

An inactive doctor returns the same 404 as an unknown one.

---

## Running locally

**Requirements:** Python 3.12, [uv](https://docs.astral.sh/uv/), Docker.

```bash
git clone https://github.com/muro906/clinic-booking-api.git
cd clinic-booking-api
cp .env.example .env            # then fill in the values (see below)
uv sync

docker compose up -d postgres   # local PostgreSQL

# Test database (tests empty their tables, so they never touch the dev database)
docker compose exec postgres psql -U <USER> -d <DB> -c "CREATE DATABASE clinic_test;"

uv run alembic upgrade head                                    # dev database
DATABASE_URL=<TEST_DATABASE_URL> uv run alembic upgrade head    # test database
uv run python -m scripts.seed                                  # five doctors

uv run uvicorn clinic_booking_api.main:app --reload            # http://localhost:8000/docs
```

**Environment variables**

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://user:password@localhost:5432/clinic`. A `postgres://` or `postgresql://` URL is rewritten to the asyncpg driver automatically, so Render's URL works unchanged. |
| `TEST_DATABASE_URL` | A separate database whose name contains "test". The test suite refuses to run otherwise. |
| `CLINIC_TIMEZONE` | Optional, defaults to `Africa/Nairobi`. Validated at startup. |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Used by Docker Compose for the local database. |

The whole stack can also run in Docker: `docker compose up --build`, then
http://localhost:8008/docs. The container runs migrations and the seed before starting.

### Tests

```bash
uv run pytest -v
```

- Normalization and schema tests need no database.
- Endpoint tests run against `TEST_DATABASE_URL`; tables are emptied before each test.
- The clock is frozen through a `get_now` dependency, so time rules ("too soon",
  "in the past") give the same result on every run.
- A concurrency test fires simultaneous bookings for one slot and checks that
  exactly one succeeds and the rest get 409.

The suite has 139 tests covering configuration, normalization, schemas, error
handling, and every endpoint, including each booking rule, token ownership,
cancel and reschedule edge cases, and the listing's minimized fields.

---

## Section 3: Deployment and CI/CD

- **Public URL:** https://clinic-booking-api-hvrp.onrender.com
- **Hosting:** Render. A Docker web service plus a Render PostgreSQL database in
  the same region, connected over the internal URL. On start, the container runs
  `alembic upgrade head`, then the idempotent seed, then uvicorn.
- **Free-tier notes:** the service sleeps after about 15 minutes idle. The free
  database was created on 20/10/2026 and expires 30 days later.

**Branch that triggers a deployment:** `main`.

**Pipeline** (`.github/workflows/`):

- **`ci.yaml`** runs on every pull request to `main`: starts a PostgreSQL service
  container, installs the locked dependencies (`uv sync --frozen`), runs
  `ruff check`, applies the migrations, and runs the full test suite.
- **`deploy.yaml`** runs on every push to `main` (a merged pull request): it reruns
  the CI workflow on the merged code, and only if that passes, calls Render's
  deploy hook, stored as the GitHub secret `RENDER_DEPLOY_HOOK_URL`. Deploys are
  serialized, so two quick merges queue rather than overlap.
- Render's auto-deploy is turned off, so the pipeline is the only path to production.
- CI runs on every pull request. Branch protection is not enabled on this
  repository, so merging is not technically blocked; I merge only after the
  check passes. Enabling a required status check on `main` is the next step.

---

## Section 4: AI reflection
I used Claude throughout, mostly as a reviewer and sparring partner, and at some
points to generate code. Below is where it helped, where it was wrong, and what I
decided myself.

**1. What I used AI for across the four sections**

- **Section 1, design:** discussing trade-offs (stored vs computed slots, which
  rules belong in the database, guest booking vs accounts, caching, async), and
  keeping a running design record that became the system design above.
- **Section 2, implementation:**
  - *Reviewing code I wrote:* config and its validators, the database session,
    the health check, the Dockerfile and Compose file, the doctor and
    working-hours models, the normalization helpers, the schemas, and the error
    classes. Most reviews found real bugs, which I fixed myself.
  - *Generating code at my request:* the patient and appointment models, the
    seed script, `conftest.py`, most test files, and a first version of the
    availability, booking, cancel, reschedule and listing services and routers.
  
- **Section 3, deployment:** reviewing my workflows and diagnosing failures from
  logs (a database password mismatch locally, missing environment variables and
  a wrong test database name in CI).
- **Section 4 and the README:** drafting this document from the design record,
  which I then edited.

**2. AI suggestions that improved my work**

- **Prompt:** I described my plan for the appointments table: a primary key of
  (patient, doctor, time slot) "to prevent double booking", and asked whether
  that was right. The answer pointed out that two different patients have
  different keys, so both could book the same slot, and that cancelled rows
  would block rebooking. It suggested a partial unique index on
  (doctor, start time) WHERE status = 'booked'. That index became the core
  concurrency guarantee of the system, and the concurrency test now proves it.
- **Prompt:** "Write tests for the rest of the schemas." The generated tests
  failed against my schemas and exposed a security bug I had written:
  `AppointmentCreated` declared `token_hash` instead of `token`, which would
  have returned the hash and never given patients their token. The same run
  showed two request schemas silently ignoring unknown fields.

**3. AI output that was wrong or incomplete, and how I caught it**

- It suggested `0700000000` as an invalid Kenyan phone number for a test. My
  test failed: 0700 is an allocated prefix, and the `phonenumbers` library
  validates against the numbering plan, not real subscribers. I replaced it
  with inputs that break the plan's rules (too short, too long, foreign) and
  documented that validation checks format, not existence.
- Its first health-check design caught only `SQLAlchemyError`. When I stopped
  the database by hand to test the 503 path, the endpoint returned 500, because
  a refused connection raised `ConnectionRefusedError`. I added `OSError`.

**4. Decisions I made without AI, and why I trusted my judgment**

- **Guest booking with a token instead of accounts.** The AI leaned towards
  minimal accounts. I chose guest booking after looking at how airlines handle
  bookings and how Kenyan clinics work: details are captured on arrival, so the
  clinic should not hold data for people who may never attend, and reviewers
  can test without credentials. I trusted this because it rests on local
  context the AI did not have.
- **An async stack.** The AI recommended sync SQLAlchemy for the deadline. I
  chose async because patient request volume is a load parameter that matters
  early, whatever the number of doctors, and accepted the extra complexity in
  sessions and tests.

Other calls I made against or without its recommendation: accepting a few
unused minutes at the edges of odd working hours to keep one global grid,
leaving the bonus listing unauthenticated with minimized fields, and rejecting
names that contain digits or underscores rather than silently changing them.