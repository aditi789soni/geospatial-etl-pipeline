"""Configuration module for geospatial ETL pipeline.

Loads environment variables, validates settings via Pydantic v2, and provides
centralized paths and credentials.
"""

from pathlib import Path
from typing import Optional
from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application settings backed by environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    ENVIRONMENT: str = Field(default="development", description="App environment")
    LOG_LEVEL: str = Field(default="INFO", description="Log level: DEBUG, INFO, WARNING, ERROR")

    # Storage Paths
    BASE_DIR: Path = BASE_DIR
    RAW_DATA_DIR: Path = BASE_DIR / "data" / "raw"
    PROCESSED_DATA_DIR: Path = BASE_DIR / "data" / "processed"

    # Database Configuration (PostGIS / PostgreSQL)
    POSTGRES_USER: str = Field(default="postgres")
    POSTGRES_PASSWORD: str = Field(default="postgres")
    POSTGRES_HOST: str = Field(default="localhost")
    POSTGRES_PORT: int = Field(default=5432)
    POSTGRES_DB: str = Field(default="geospatial_db")

    @property
    def database_url(self) -> str:
        """Construct PostgreSQL connection string."""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Google Earth Engine (GEE)
    GEE_SERVICE_ACCOUNT: Optional[str] = Field(
        default=None, description="Service account email for GEE"
    )
    GEE_PRIVATE_KEY_PATH: Optional[str] = Field(
        default=None, description="Path to GEE service account private key JSON"
    )
    GEE_PROJECT_ID: Optional[str] = Field(
        default=None, description="Google Cloud Project ID enabled for GEE"
    )

    # Copernicus / SciHub / Sentinel Data Hub
    COPERNICUS_USERNAME: Optional[str] = Field(default=None)
    COPERNICUS_PASSWORD: Optional[str] = Field(default=None)

    # Open-Meteo REST API
    OPEN_METEO_BASE_URL: str = Field(
        default="https://api.open-meteo.com/v1/forecast",
        description="Base URL for Open-Meteo weather API",
    )

    # Pipeline Defaults
    DEFAULT_EPSG: int = Field(default=32643, description="Default target CRS (UTM Zone 43N)")
    MAX_CLOUD_COVER: float = Field(default=20.0, description="Maximum cloud coverage threshold in percent")


# Instantiate singleton settings
settings = Settings()

# Ensure directories exist
settings.RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
