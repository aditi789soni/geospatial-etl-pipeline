"""Spatial clipping module for rasters using vector geometries."""

from pathlib import Path
from typing import List, Optional, Union
import geopandas as gpd
import rasterio
from rasterio.mask import mask
from shapely.geometry import Polygon, mapping
from src.utils.logger import setup_logger

logger = setup_logger("clip")


def clip_raster_with_geometry(
    input_raster_path: Union[str, Path],
    output_raster_path: Union[str, Path],
    geometries: List[Union[Polygon, dict]],
    crop: bool = True,
) -> Path:
    """Clips an input GeoTIFF using Shapely polygons or GeoJSON-like dict geometries.

    Ensures geometries match raster projection before masking.
    """
    input_p = Path(input_raster_path)
    out_p = Path(output_raster_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    # Standardize geometries to mapping format
    shapes = [
        geom if isinstance(geom, dict) else mapping(geom)
        for geom in geometries
    ]

    with rasterio.open(input_p) as src:
        out_image, out_transform = mask(src, shapes=shapes, crop=crop, all_touched=True)
        out_meta = src.meta.copy()

        out_meta.update(
            {
                "driver": "GTiff",
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform,
            }
        )

        with rasterio.open(out_p, "w", **out_meta) as dst:
            dst.write(out_image)

    logger.info(f"Clipped raster saved to {out_p.name} with shape {out_image.shape}")
    return out_p


def clip_raster_with_vector_file(
    input_raster_path: Union[str, Path],
    vector_path: Union[str, Path],
    output_raster_path: Union[str, Path],
    crop: bool = True,
) -> Path:
    """Clips a GeoTIFF using a vector file (Shapefile, GeoJSON, Geopackage).

    Automatically transforms vector CRS to match the raster CRS.
    """
    gdf = gpd.read_file(vector_path)
    with rasterio.open(input_raster_path) as src:
        raster_crs = src.crs

    if gdf.crs != raster_crs:
        logger.info(f"Reprojecting vector geometries from {gdf.crs} to {raster_crs}")
        gdf = gdf.to_crs(raster_crs)

    geoms = [geom for geom in gdf.geometry if geom.is_valid and not geom.is_empty]
    return clip_raster_with_geometry(input_raster_path, output_raster_path, geoms, crop=crop)
