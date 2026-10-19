"""Unit and integration tests for extraction modules (GEE, SentinelHub, Weather)."""

import pytest
from src.extract.gee_downloader import GEEDownloader
from src.extract.weather_api import WeatherExtractor
from src.extract.sentinel_api import SentinelAPIClient


def test_weather_extractor():
    """Validates Open-Meteo weather data extraction."""
    extractor = WeatherExtractor()
    data = extractor.fetch_weather_for_point(latitude=12.97, longitude=77.59)

    assert "temperature_celsius" in data
    assert "relative_humidity_pct" in data
    assert "cloud_cover_pct" in data
    assert isinstance(data["temperature_celsius"], (int, float))
    assert -50 <= data["temperature_celsius"] <= 60


def test_gee_downloader_simulation_mode(tmp_path):
    """Validates GEE downloader catalog search and synthetic band extraction."""
    downloader = GEEDownloader()
    bbox = (77.5, 12.9, 77.7, 13.1)

    scenes = downloader.search_sentinel2(
        bbox=bbox,
        start_date="2023-06-01",
        end_date="2023-06-30",
        max_cloud_cover=20.0,
    )
    assert len(scenes) > 0
    assert "id" in scenes[0]

    # Test band downloads (or synthetic generation)
    bands = downloader.download_bands(
        scene_id=scenes[0]["id"],
        bbox=bbox,
        bands=["B4", "B8", "SCL"],
        output_dir=tmp_path,
    )
    assert "B4" in bands
    assert "B8" in bands
    assert "SCL" in bands
    assert bands["B4"].exists()
    assert bands["B8"].exists()
    assert bands["SCL"].exists()


def test_sentinelsat_query_fallback():
    """Validates Sentinel-2 Copernicus client query fallback."""
    client = SentinelAPIClient()
    products = client.query_products(
        geojson_polygon="POLYGON((77.5 12.9, 77.7 12.9, 77.7 13.1, 77.5 13.1, 77.5 12.9))",
        start_date="2023-06-01",
        end_date="2023-06-30",
    )
    assert isinstance(products, list)
    assert len(products) > 0
    assert "title" in products[0]
