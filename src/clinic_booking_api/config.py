from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn, field_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from functools import lru_cache


class Settings(BaseSettings):
    database_url: PostgresDsn

    # Apply a fieldvalidator that ensures that the database url has the scheme postgresql+asyncpg
    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, url) -> str:
        if not isinstance(url, str):
            raise ValueError("The value provided is not a valid database url string")
        url = url.strip()
        prefixes = ["postgres://", "postgresql://"]
        new = "postgresql+asyncpg://"
        for prefix in prefixes:
            if url.startswith(prefix):
                url = new + url.removeprefix(prefix)
        if not url.startswith(new):
            raise ValueError(
                "The dialect+driver for the database is 'postgresql+asyncpg'"
            )
        return url

    clinic_timezone: str = "Africa/Nairobi"

    # Apply a field validator that checks IANA timezone strings are valid ZoneInfo objects
    @field_validator("clinic_timezone", mode="after")
    @classmethod
    def validate_timezone(cls, value) -> str:
        try:
            ZoneInfo(value)
            return value
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"{value} is not a valid IANA timezone string. {e}")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings():
    return Settings()
