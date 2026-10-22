FROM python:3.12-slim

WORKDIR /code

# Set env variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create non-root user
RUN groupadd --system fastapi && useradd --system -g fastapi -M -s /usr/sbin/nologin fastapi

# Install Dependencies
COPY requirements.txt .

# Install dependencies (run as root so packages install correctly)
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files and change ownership to non-root user
COPY --chown=fastapi:fastapi ./src/clinic_booking_api /code/clinic_booking_api

COPY --chown=fastapi:fastapi  alembic.ini .
COPY --chown=fastapi:fastapi migrations/ ./migrations/
COPY --chown=fastapi:fastapi scripts/ ./scripts/

# Switch to non-root user for security purposes
USER fastapi

# Expose fastapi port
EXPOSE 8000

# Start Uvicorn
CMD ["sh", "-c", "alembic upgrade head && python -m scripts.seed && exec uvicorn clinic_booking_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
