"""Database loader module with SQLAlchemy and GeoAlchemy2.

Manages relational and PostGIS spatial entities for satellite scenes,
including bounding box polygons (with spatial indexes) and spectral statistics.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from geoalchemy2 import Geometry
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.orm import declarative_base, sessionmaker
from src.utils.config import settings
from src.utils.logger import setup_logger

logger = setup_logger("db_loader")

Base = declarative_base()


class SatelliteRasterMetadata(Base):
    """PostGIS ORM table storing raster scene metadata, spatial footprints,

    and calculated indices statistics.
    """

    __tablename__ = "satellite_raster_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scene_id = Column(String(255), unique=True, nullable=False, index=True)
    satellite_name = Column(String(50), default="Sentinel-2", nullable=False)
    acquisition_date = Column(DateTime, nullable=False, index=True)
    cloud_cover_pct = Column(Float, nullable=False)
    epsg_crs = Column(Integer, nullable=False)

    # PostGIS Polygon geometry with WGS84 CRS (EPSG:4326)
    footprint = Column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True),
        nullable=False,
    )

    # File paths
    raw_file_path = Column(Text, nullable=True)
    processed_cog_path = Column(Text, nullable=False)

    # NDVI Summary Metrics
    ndvi_min = Column(Float, nullable=True)
    ndvi_max = Column(Float, nullable=True)
    ndvi_mean = Column(Float, nullable=True)
    ndvi_std = Column(Float, nullable=True)
    valid_pixel_pct = Column(Float, nullable=True)

    # Auxiliary atmospheric metrics
    temperature_celsius = Column(Float, nullable=True)
    relative_humidity_pct = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Spatial GIST Index is automatically created by GeoAlchemy2,
    # adding composite index on date and satellite
    __table_args__ = (
        Index("idx_satellite_date", "satellite_name", "acquisition_date"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes record to standard Python dictionary."""
        return {
            "id": self.id,
            "scene_id": self.scene_id,
            "satellite_name": self.satellite_name,
            "acquisition_date": self.acquisition_date.isoformat() if self.acquisition_date else None,
            "cloud_cover_pct": self.cloud_cover_pct,
            "epsg_crs": self.epsg_crs,
            "processed_cog_path": self.processed_cog_path,
            "ndvi_mean": self.ndvi_mean,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DatabaseManager:
    """Manages connections, schema initialization, and transactional persistence to PostGIS."""

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or settings.database_url
        self.engine = create_engine(self.db_url, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def init_db(self) -> None:
        """Initializes tables and confirms PostGIS extension availability."""
        try:
            with self.engine.connect() as conn:
                conn.execute(func.text("CREATE EXTENSION IF NOT EXISTS postgis;"))
                conn.commit()
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database schema and PostGIS extension verified.")
        except Exception as exc:
            logger.warning(f"Could not connect to live PostGIS DB ({exc}). Offline/Mock DB mode available.")

    def insert_raster_metadata(
        self,
        scene_id: str,
        acquisition_date: datetime,
        cloud_cover_pct: float,
        epsg_crs: int,
        footprint_wkt: str,
        processed_cog_path: str,
        ndvi_stats: Dict[str, float],
        raw_file_path: Optional[str] = None,
        weather_metrics: Optional[Dict[str, float]] = None,
    ) -> SatelliteRasterMetadata:
        """Persists satellite scene record with PostGIS ST_GeomFromText geometry."""
        session = self.SessionLocal()
        try:
            record = (
                session.query(SatelliteRasterMetadata)
                .filter(SatelliteRasterMetadata.scene_id == scene_id)
                .first()
            )

            if not record:
                record = SatelliteRasterMetadata(scene_id=scene_id)
                session.add(record)

            record.acquisition_date = acquisition_date
            record.cloud_cover_pct = cloud_cover_pct
            record.epsg_crs = epsg_crs
            record.footprint = func.ST_GeomFromText(footprint_wkt, 4326)
            record.raw_file_path = raw_file_path
            record.processed_cog_path = str(processed_cog_path)

            if ndvi_stats:
                record.ndvi_min = ndvi_stats.get("min")
                record.ndvi_max = ndvi_stats.get("max")
                record.ndvi_mean = ndvi_stats.get("mean")
                record.ndvi_std = ndvi_stats.get("std")
                record.valid_pixel_pct = ndvi_stats.get("valid_percentage")

            if weather_metrics:
                record.temperature_celsius = weather_metrics.get("temperature_celsius")
                record.relative_humidity_pct = weather_metrics.get("relative_humidity_pct")

            session.commit()
            session.refresh(record)
            logger.info(f"Persisted raster record: {scene_id} (ID: {record.id})")
            return record
        except Exception as exc:
            session.rollback()
            logger.error(f"Failed to persist raster metadata for {scene_id}: {exc}")
            raise
        finally:
            session.close()

    def query_by_point_radius(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
    ) -> List[SatelliteRasterMetadata]:
        """Performs spatial query using PostGIS ST_DWithin on geography or transformed geometry."""
        session = self.SessionLocal()
        try:
            point_geom = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)
            # 1 degree ~= 111320 meters, or ST_DWithin with geography
            results = (
                session.query(SatelliteRasterMetadata)
                .filter(
                    func.ST_DWithin(
                        func.ST_Transform(SatelliteRasterMetadata.footprint, 3857),
                        func.ST_Transform(point_geom, 3857),
                        radius_km * 1000.0,
                    )
                )
                .all()
            )
            return results
        finally:
            session.close()


db_manager = DatabaseManager()
