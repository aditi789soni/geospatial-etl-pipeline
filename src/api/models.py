"""Pydantic data schemas for Geospatial REST API."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BoundingBoxQuery(BaseModel):
    """Bounding box coordinates [min_lon, min_lat, max_lon, max_lat]."""

    min_lon: float = Field(..., ge=-180.0, le=180.0, description="Minimum longitude")
    min_lat: float = Field(..., ge=-90.0, le=90.0, description="Minimum latitude")
    max_lon: float = Field(..., ge=-180.0, le=180.0, description="Maximum longitude")
    max_lat: float = Field(..., ge=-90.0, le=90.0, description="Maximum latitude")


class SpatialRadiusQuery(BaseModel):
    """Centroid coordinates and search radius."""

    latitude: float = Field(..., ge=-90.0, le=90.0, description="Center latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Center longitude")
    radius_km: float = Field(default=15.0, gt=0, le=500.0, description="Search radius in kilometers")
    start_date: Optional[str] = Field(default=None, description="ISO format start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(default=None, description="ISO format end date (YYYY-MM-DD)")


class RasterMetadataResponse(BaseModel):
    """Response model for satellite scene and NDVI metadata."""

    id: int
    scene_id: str
    satellite_name: str
    acquisition_date: Optional[str]
    cloud_cover_pct: float
    epsg_crs: int
    processed_cog_path: str
    ndvi_mean: Optional[float] = None
    ndvi_min: Optional[float] = None
    ndvi_max: Optional[float] = None
    temperature_celsius: Optional[float] = None
    created_at: Optional[str] = None


class PipelineRunRequest(BaseModel):
    """Payload to trigger an ad-hoc pipeline execution run."""

    min_lon: float = Field(default=77.50)
    min_lat: float = Field(default=12.90)
    max_lon: float = Field(default=77.75)
    max_lat: float = Field(default=13.10)
    start_date: str = Field(default="2023-06-01")
    end_date: str = Field(default="2023-06-30")
    target_epsg: int = Field(default=32643)


class PipelineRunResponse(BaseModel):
    """Response from executing an on-demand ETL pipeline run."""

    status: str
    scene_id: str
    cog_file: str
    ndvi_mean: Optional[float] = None
    db_record_id: Optional[int] = None
