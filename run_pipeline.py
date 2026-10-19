"""Standalone CLI execution runner for the geospatial ETL pipeline.

Runs the complete lifecycle without requiring an active Airflow scheduler:
Extract -> Transform (Mask, NDVI, Reproject) -> Quality Check -> COG -> PostGIS Load.
"""

import argparse
from datetime import datetime
from pathlib import Path
import sys

# Ensure root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.extract.gee_downloader import GEEDownloader
from src.extract.weather_api import WeatherExtractor
from src.load.cog_converter import convert_to_cog
from src.load.db_loader import DatabaseManager
from src.load.file_manager import FileManager
from src.transform.cloud_mask import mask_raster_file
from src.transform.indices import compute_raster_ndvi_file
from src.transform.quality_check import validate_ndvi_quality
from src.transform.reproject import reproject_raster
from src.utils.config import settings
from src.utils.geo_utils import bbox_to_polygon
from src.utils.logger import setup_logger

logger = setup_logger("standalone_runner")


def run_full_pipeline(
    min_lon: float = 77.50,
    min_lat: float = 12.90,
    max_lon: float = 77.75,
    max_lat: float = 13.10,
    start_date: str = "2023-06-01",
    end_date: str = "2023-06-30",
    max_cloud_cover: float = 20.0,
    target_epsg: int = 32643,
) -> dict:
    """Executes the end-to-end geospatial ETL pipeline for specified bounding coordinates."""
    logger.info("===================================================================")
    logger.info("   STARTING GEOSPATIAL SENTINEL-2 NDVI PIPELINE (STANDALONE)      ")
    logger.info("===================================================================")

    bbox = (min_lon, min_lat, max_lon, max_lat)
    logger.info(f"Target Bounding Box: {bbox} | CRS: EPSG:{target_epsg}")

    # Step 1: Extraction
    logger.info(">>> STEP 1: Extracting Satellite Imagery & Auxiliary Data")
    downloader = GEEDownloader()
    scenes = downloader.search_sentinel2(
        bbox=bbox,
        start_date=start_date,
        end_date=end_date,
        max_cloud_cover=max_cloud_cover,
    )
    if not scenes:
        raise RuntimeError("No candidate satellite scenes found matching criteria.")

    chosen_scene = scenes[0]["id"]
    cloud_cover_pct = scenes[0].get("cloud_cover", 10.0)
    logger.info(f"Selected Scene: {chosen_scene} (Cloud Cover: {cloud_cover_pct}%)")

    bands = downloader.download_bands(
        scene_id=chosen_scene,
        bbox=bbox,
        bands=["B2", "B3", "B4", "B8", "SCL"],
    )

    # Auxiliary weather fetch
    center_lat = (min_lat + max_lat) / 2.0
    center_lon = (min_lon + max_lon) / 2.0
    weather = WeatherExtractor().fetch_weather_for_point(center_lat, center_lon)

    # Step 2: Transformation
    logger.info(">>> STEP 2: Transforming Spectral Bands & Cloud Masking")
    processed_dir = settings.PROCESSED_DATA_DIR
    masked_nir = processed_dir / "temp_masked_nir.tif"
    masked_red = processed_dir / "temp_masked_red.tif"

    mask_raster_file(bands["B8"], bands["SCL"], masked_nir)
    mask_raster_file(bands["B4"], bands["SCL"], masked_red)

    logger.info(">>> STEP 2b: Computing Vectorized NDVI")
    raw_ndvi = processed_dir / "temp_raw_ndvi.tif"
    _, ndvi_stats = compute_raster_ndvi_file(masked_nir, masked_red, raw_ndvi)

    logger.info(f">>> STEP 2c: Reprojecting to Target CRS (EPSG:{target_epsg})")
    reprojected_ndvi = processed_dir / "temp_reprojected_ndvi.tif"
    reproject_raster(raw_ndvi, reprojected_ndvi, target_epsg=target_epsg)

    # Step 3: Quality Assurance Check
    logger.info(">>> STEP 3: Executing Quality Assurance Sanity Checks")
    qa_report = validate_ndvi_quality(reprojected_ndvi, min_valid_pct=5.0)
    logger.info(f"Quality Check Results: {qa_report}")

    # Step 4: Load & Storage Management
    logger.info(">>> STEP 4: Converting to Cloud-Optimized GeoTIFF (COG)")
    fm = FileManager()
    final_cog_path = fm.generate_processed_path(scene_id=chosen_scene, product_name="NDVI_COG")
    convert_to_cog(reprojected_ndvi, final_cog_path, profile_name="deflate")

    logger.info(">>> STEP 4b: Persisting Geospatial Metadata to PostGIS")
    polygon = bbox_to_polygon(*bbox)
    db = DatabaseManager()
    db.init_db()

    record = None
    try:
        record = db.insert_raster_metadata(
            scene_id=chosen_scene,
            acquisition_date=datetime.utcnow(),
            cloud_cover_pct=cloud_cover_pct,
            epsg_crs=target_epsg,
            footprint_wkt=polygon.wkt,
            processed_cog_path=str(final_cog_path),
            ndvi_stats=ndvi_stats,
            raw_file_path=str(bands.get("B8")),
            weather_metrics=weather,
        )
        logger.info(f"Database record inserted with ID: {record.id}")
    except Exception as exc:
        logger.warning(f"Could not write to PostGIS DB ({exc}). Pipeline proceeding with local COG output.")

    # Cleanup intermediate scratch files
    fm.clean_temporary_files(prefix="temp_")

    logger.info("===================================================================")
    logger.info("            PIPELINE EXECUTION SUCCESSFULLY COMPLETED             ")
    logger.info(f"Output COG File: {final_cog_path}")
    logger.info("===================================================================")

    return {
        "status": "SUCCESS",
        "scene_id": chosen_scene,
        "cog_file": str(final_cog_path),
        "ndvi_mean": ndvi_stats.get("mean"),
        "db_record_id": record.id if record else None,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Sentinel-2 Geospatial ETL Pipeline CLI")
    parser.add_argument("--min-lon", type=float, default=77.50, help="Bounding box min longitude")
    parser.add_argument("--min-lat", type=float, default=12.90, help="Bounding box min latitude")
    parser.add_argument("--max-lon", type=float, default=77.75, help="Bounding box max longitude")
    parser.add_argument("--max-lat", type=float, default=13.10, help="Bounding box max latitude")
    parser.add_argument("--start-date", type=str, default="2023-06-01", help="Acquisition start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default="2023-06-30", help="Acquisition end date (YYYY-MM-DD)")
    parser.add_argument("--epsg", type=int, default=32643, help="Target projection EPSG code")

    args = parser.parse_args()

    run_full_pipeline(
        min_lon=args.min_lon,
        min_lat=args.min_lat,
        max_lon=args.max_lon,
        max_lat=args.max_lat,
        start_date=args.start_date,
        end_date=args.end_date,
        target_epsg=args.epsg,
    )
