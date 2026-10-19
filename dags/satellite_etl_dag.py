"""Apache Airflow DAG orchestrating the end-to-end Geospatial Satellite ETL Pipeline.

Flow:
1. Extract Sentinel-2 Imagery (GEE or Copernicus) & Meteorological Data
2. Transform: Cloud Masking -> Spectral Indices (NDVI) -> Reprojection -> Spatial Clipping
3. Quality Assurance Check (Sanity & Threshold validation)
4. Load: COG Generation -> PostGIS Metadata Ingestion
5. Notification: Health status and metrics reporting
"""

from datetime import datetime, timedelta
import os
from pathlib import Path
from airflow.decorators import dag, task
from airflow.operators.empty import EmptyOperator

# Pipeline Default Arguments
default_args = {
    "owner": "geospatial_eng",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


@dag(
    dag_id="satellite_sentinel2_etl_pipeline",
    default_args=default_args,
    description="Automated Sentinel-2 L2A ingest, index computation, COG packaging, and PostGIS loader",
    schedule_interval="0 6 * * *",  # Daily at 06:00 UTC
    start_date=datetime(2023, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["geospatial", "earth-observation", "sentinel-2", "postgis", "ndvi"],
)
def satellite_etl_pipeline():
    """Defines the TaskFlow execution graph for the Geospatial ETL."""

    start_pipeline = EmptyOperator(task_id="start_pipeline")

    @task(task_id="extract_satellite_and_weather")
    def extract_task() -> dict:
        """Downloads Sentinel-2 bands and fetches co-located weather observations."""
        from src.extract.gee_downloader import GEEDownloader
        from src.extract.weather_api import WeatherExtractor
        from src.utils.logger import setup_logger

        log = setup_logger("airflow.extract")
        log.info("Starting satellite band extraction...")

        bbox = (77.50, 12.90, 77.75, 13.10)  # Bangalore urban/rural fringe test ROI
        downloader = GEEDownloader()
        scenes = downloader.search_sentinel2(
            bbox=bbox,
            start_date="2023-06-01",
            end_date="2023-06-30",
            max_cloud_cover=20.0,
        )
        selected_scene = scenes[0]["id"]
        bands = downloader.download_bands(
            scene_id=selected_scene,
            bbox=bbox,
            bands=["B2", "B3", "B4", "B8", "SCL"],
        )

        weather = WeatherExtractor().fetch_weather_for_point(latitude=13.0, longitude=77.6)

        return {
            "scene_id": selected_scene,
            "bbox": list(bbox),
            "cloud_cover": scenes[0].get("cloud_cover", 10.0),
            "band_files": {k: str(v) for k, v in bands.items()},
            "weather": weather,
        }

    @task(task_id="transform_indices_and_mask")
    def transform_task(extract_meta: dict) -> dict:
        """Applies SCL cloud masking, computes NDVI, and reprojects to target UTM CRS."""
        from src.transform.cloud_mask import mask_raster_file
        from src.transform.indices import compute_raster_ndvi_file
        from src.transform.reproject import reproject_raster
        from src.utils.config import settings

        band_files = extract_meta["band_files"]
        processed_dir = settings.PROCESSED_DATA_DIR
        raw_nir = band_files["B8"]
        raw_red = band_files["B4"]
        raw_scl = band_files["SCL"]

        # 1. Mask NIR and Red bands
        masked_nir = processed_dir / "masked_nir.tif"
        masked_red = processed_dir / "masked_red.tif"
        mask_raster_file(raw_nir, raw_scl, masked_nir)
        mask_raster_file(raw_red, raw_scl, masked_red)

        # 2. Compute NDVI
        raw_ndvi = processed_dir / "raw_ndvi.tif"
        _, ndvi_stats = compute_raster_ndvi_file(masked_nir, masked_red, raw_ndvi)

        # 3. Reproject to target UTM Zone (EPSG:32643)
        utm_ndvi = processed_dir / "utm_ndvi.tif"
        reproject_raster(raw_ndvi, utm_ndvi, target_epsg=settings.DEFAULT_EPSG)

        return {
            **extract_meta,
            "transformed_raster": str(utm_ndvi),
            "ndvi_stats": ndvi_stats,
            "target_epsg": settings.DEFAULT_EPSG,
        }

    @task(task_id="quality_assurance_check")
    def quality_check_task(transform_meta: dict) -> dict:
        """Runs rigorous data sanity and distribution checks on the transformed NDVI raster."""
        from src.transform.quality_check import validate_ndvi_quality

        raster_path = transform_meta["transformed_raster"]
        report = validate_ndvi_quality(raster_path, min_valid_pct=5.0)

        return {
            **transform_meta,
            "quality_report": report,
        }

    @task(task_id="load_cog_and_database")
    def load_task(qa_meta: dict) -> dict:
        """Converts output to Cloud Optimized GeoTIFF (COG) and persists metadata into PostGIS."""
        from src.load.cog_converter import convert_to_cog
        from src.load.db_loader import DatabaseManager
        from src.load.file_manager import FileManager
        from src.utils.geo_utils import bbox_to_polygon

        input_raster = qa_meta["transformed_raster"]
        scene_id = qa_meta["scene_id"]
        bbox = qa_meta["bbox"]

        # COG Conversion
        fm = FileManager()
        target_cog_path = fm.generate_processed_path(scene_id=scene_id, product_name="NDVI_COG")
        convert_to_cog(input_raster, target_cog_path, profile_name="deflate")

        # PostGIS Geometry
        geom = bbox_to_polygon(bbox[0], bbox[1], bbox[2], bbox[3])
        wkt_polygon = geom.wkt

        # DB Insertion
        db = DatabaseManager()
        db.init_db()
        record = db.insert_raster_metadata(
            scene_id=scene_id,
            acquisition_date=datetime.utcnow(),
            cloud_cover_pct=qa_meta["cloud_cover"],
            epsg_crs=qa_meta["target_epsg"],
            footprint_wkt=wkt_polygon,
            processed_cog_path=str(target_cog_path),
            ndvi_stats=qa_meta["ndvi_stats"],
            weather_metrics=qa_meta.get("weather"),
        )

        return {
            "record_id": record.id if hasattr(record, "id") else 1,
            "scene_id": scene_id,
            "cog_path": str(target_cog_path),
            "status": "LOADED",
        }

    @task(task_id="pipeline_notification")
    def notify_task(load_meta: dict) -> None:
        """Final notification task logging success status and summary telemetry."""
        from src.utils.logger import setup_logger

        logger = setup_logger("airflow.notify")
        logger.info(
            f"Pipeline successfully completed! Scene: {load_meta['scene_id']} | "
            f"COG Stored: {load_meta['cog_path']} | DB Record: {load_meta['record_id']}"
        )

    end_pipeline = EmptyOperator(task_id="end_pipeline")

    # Flow Graph Definition
    ext_data = extract_task()
    trans_data = transform_task(ext_data)
    qa_data = quality_check_task(trans_data)
    load_res = load_task(qa_data)
    notif = notify_task(load_res)

    start_pipeline >> ext_data
    notif >> end_pipeline


pipeline = satellite_etl_pipeline()
