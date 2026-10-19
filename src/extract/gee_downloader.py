"""Extract module for downloading Sentinel-2 surface reflectance imagery via Google Earth Engine (GEE)."""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests
from src.utils.config import settings
from src.utils.logger import setup_logger

logger = setup_logger("gee_downloader")

try:
    import ee
except ImportError:
    ee = None  # Handled gracefully if earthengine-api isn't installed in lightweight environments


class GEEDownloader:
    """Handles authentication, catalog search, and band extraction from Google Earth Engine."""

    def __init__(self, project_id: Optional[str] = None):
        self.project_id = project_id or settings.GEE_PROJECT_ID
        self.is_authenticated = False
        self._authenticate()

    def _authenticate(self) -> None:
        """Authenticates with Earth Engine using Service Account credentials or user ADC."""
        if ee is None:
            logger.warning("Earth Engine library not installed. Mock or fallback extraction required.")
            return

        try:
            if settings.GEE_SERVICE_ACCOUNT and settings.GEE_PRIVATE_KEY_PATH:
                if os.path.exists(settings.GEE_PRIVATE_KEY_PATH):
                    credentials = ee.ServiceAccountCredentials(
                        settings.GEE_SERVICE_ACCOUNT, settings.GEE_PRIVATE_KEY_PATH
                    )
                    ee.Initialize(credentials, project=self.project_id)
                    self.is_authenticated = True
                    logger.info("Successfully authenticated GEE via Service Account.")
                    return
            
            # Default initialization
            if self.project_id:
                ee.Initialize(project=self.project_id)
            else:
                ee.Initialize()
            self.is_authenticated = True
            logger.info("Successfully initialized GEE environment.")
        except Exception as exc:
            logger.warning(f"GEE Initialization skipped or failed ({exc}). Mock/fallback mode enabled.")
            self.is_authenticated = False

    def search_sentinel2(
        self,
        bbox: Tuple[float, float, float, float],
        start_date: str,
        end_date: str,
        max_cloud_cover: float = 20.0,
    ) -> List[Dict]:
        """Queries COPERNICUS/S2_SR_HARMONIZED for valid scenes within bbox and date range."""
        if not self.is_authenticated:
            logger.info("GEE not authenticated. Returning simulated Sentinel-2 scene metadata.")
            return [
                {
                    "id": "COPERNICUS/S2_SR_HARMONIZED/20230615T052651_20230615T053428_T43REQ",
                    "date": "2023-06-15",
                    "cloud_cover": 8.5,
                    "bbox": bbox,
                }
            ]

        minx, miny, maxx, maxy = bbox
        geometry = ee.Geometry.Rectangle([minx, miny, maxx, maxy])

        collection = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(geometry)
            .filterDate(start_date, end_date)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud_cover))
            .sort("CLOUDY_PIXEL_PERCENTAGE")
        )

        count = collection.size().getInfo()
        logger.info(f"Found {count} candidate Sentinel-2 scenes in GEE.")

        scenes = []
        image_list = collection.toList(count)
        for i in range(min(count, 10)):  # Top 10 clearest
            img = ee.Image(image_list.get(i))
            info = img.getInfo()
            props = info.get("properties", {})
            scenes.append(
                {
                    "id": info.get("id"),
                    "date": props.get("DATATAKE_IDENTIFIER", "UNKNOWN"),
                    "cloud_cover": props.get("CLOUDY_PIXEL_PERCENTAGE", 0.0),
                    "bbox": bbox,
                }
            )
        return scenes

    def download_bands(
        self,
        scene_id: str,
        bbox: Tuple[float, float, float, float],
        bands: List[str] = ("B2", "B3", "B4", "B8", "SCL"),
        output_dir: Optional[Path] = None,
        scale: int = 10,
    ) -> Dict[str, Path]:
        """Downloads individual spectral bands as GeoTIFF files to output_dir.

        Falls back to generating synthetic calibrated Sentinel-2 bands if GEE is offline.
        """
        target_dir = Path(output_dir or settings.RAW_DATA_DIR)
        target_dir.mkdir(parents=True, exist_ok=True)
        downloaded = {}

        if not self.is_authenticated:
            logger.info("Generating calibrated synthetic Sentinel-2 GeoTIFF bands for offline testing.")
            return self._generate_synthetic_bands(target_dir, bbox, bands)

        minx, miny, maxx, maxy = bbox
        roi = ee.Geometry.Rectangle([minx, miny, maxx, maxy])
        image = ee.Image(scene_id).select(list(bands))

        for band in bands:
            band_file = target_dir / f"{scene_id.replace('/', '_')}_{band}.tif"
            if band_file.exists():
                logger.info(f"Band {band} already downloaded: {band_file.name}")
                downloaded[band] = band_file
                continue

            band_img = image.select(band)
            url = band_img.getDownloadURL(
                {
                    "name": f"{band}",
                    "scale": scale,
                    "crs": "EPSG:4326",
                    "region": roi,
                    "format": "GEO_TIFF",
                }
            )
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()

            with open(band_file, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)

            logger.info(f"Downloaded band {band} to {band_file}")
            downloaded[band] = band_file

        return downloaded

    def _generate_synthetic_bands(
        self,
        output_dir: Path,
        bbox: Tuple[float, float, float, float],
        bands: List[str],
    ) -> Dict[str, Path]:
        """Generates realistic synthetic Sentinel-2 GeoTIFFs (B2, B3, B4, B8, SCL)

        with proper georeferencing transform and metadata.
        """
        import numpy as np
        import rasterio
        from rasterio.transform import from_bounds

        minx, miny, maxx, maxy = bbox
        width, height = 256, 256
        transform = from_bounds(minx, miny, maxx, maxy, width, height)
        downloaded = {}

        # Consistent synthetic spatial patterns
        np.random.seed(42)
        x = np.linspace(0, 4 * np.pi, width)
        y = np.linspace(0, 4 * np.pi, height)
        xx, yy = np.meshgrid(x, y)
        pattern = np.sin(xx) * np.cos(yy)

        for band in bands:
            band_path = output_dir / f"synthetic_{band}.tif"
            if band == "B2":  # Blue (490 nm)
                arr = (1000 + 400 * pattern + np.random.normal(0, 50, (height, width))).astype(np.uint16)
            elif band == "B3":  # Green (560 nm)
                arr = (1200 + 500 * pattern + np.random.normal(0, 50, (height, width))).astype(np.uint16)
            elif band == "B4":  # Red (665 nm)
                arr = (1100 + 600 * pattern + np.random.normal(0, 50, (height, width))).astype(np.uint16)
            elif band == "B8":  # NIR (842 nm) - healthy vegetation reflects high NIR
                arr = (3500 + 1200 * pattern + np.random.normal(0, 80, (height, width))).astype(np.uint16)
            elif band == "SCL":  # Scene Classification Layer (SCL)
                # 4: Vegetation, 5: Bare soils, 9: Cloud high prob, 8: Cloud medium prob
                arr = np.full((height, width), 4, dtype=np.uint8)
                arr[height // 4 : height // 3, width // 4 : width // 3] = 9  # simulated cloud
                arr[height // 2 : height // 2 + 20, width // 2 : width // 2 + 20] = 3  # cloud shadow
            else:
                arr = (1000 + 200 * pattern).astype(np.uint16)

            dtype = "uint8" if band == "SCL" else "uint16"
            with rasterio.open(
                band_path,
                "w",
                driver="GTiff",
                height=height,
                width=width,
                count=1,
                dtype=dtype,
                crs="EPSG:4326",
                transform=transform,
                nodata=0,
            ) as dst:
                dst.write(arr, 1)

            downloaded[band] = band_path
            logger.info(f"Generated synthetic GeoTIFF band [{band}] at {band_path.name}")

        return downloaded
