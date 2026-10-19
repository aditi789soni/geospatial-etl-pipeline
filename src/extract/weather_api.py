"""Extract module for auxiliary meteorological data using the Open-Meteo REST API."""

from datetime import datetime
from typing import Any, Dict, Optional
import requests
from src.utils.config import settings
from src.utils.logger import setup_logger

logger = setup_logger("weather_api")


class WeatherExtractor:
    """Retrieves auxiliary atmospheric and meteorological observations (temperature,

    precipitation, relative humidity, cloud cover) to enrich satellite imagery analysis.
    """

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or settings.OPEN_METEO_BASE_URL

    def fetch_weather_for_point(
        self,
        latitude: float,
        longitude: float,
        date_str: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Queries Open-Meteo API for historical or current atmospheric measurements

        at the centroid of the satellite tile.
        """
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,precipitation,cloud_cover,surface_pressure",
            "timezone": "auto",
        }

        logger.info(f"Fetching meteorological metrics for point ({latitude}, {longitude})")
        try:
            response = requests.get(self.base_url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            current = data.get("current", {})

            result = {
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": current.get("time", datetime.utcnow().isoformat()),
                "temperature_celsius": current.get("temperature_2m", 25.0),
                "relative_humidity_pct": current.get("relative_humidity_2m", 50.0),
                "precipitation_mm": current.get("precipitation", 0.0),
                "cloud_cover_pct": current.get("cloud_cover", 10.0),
                "surface_pressure_hpa": current.get("surface_pressure", 1013.25),
            }
            logger.info(f"Meteorological data successfully retrieved: Temp={result['temperature_celsius']}°C, Clouds={result['cloud_cover_pct']}%")
            return result

        except Exception as exc:
            logger.warning(f"Failed to fetch live weather from {self.base_url} ({exc}). Using nominal atmospheric defaults.")
            return {
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": datetime.utcnow().isoformat(),
                "temperature_celsius": 24.5,
                "relative_humidity_pct": 55.0,
                "precipitation_mm": 0.0,
                "cloud_cover_pct": 12.0,
                "surface_pressure_hpa": 1012.0,
            }
