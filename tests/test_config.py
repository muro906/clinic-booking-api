import pytest
from pydantic import ValidationError

from clinic_booking_api.config import Settings

def test_postgres_scheme_is_rewritten():
    settings = Settings(database_url="postgres://user:pw@host:5432/db", _env_file=None)
    assert str(settings.database_url) == "postgresql+asyncpg://user:pw@host:5432/db"
def test_wrong_driver_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="mysql+mysqldb://user:pw@host:5432/db")
