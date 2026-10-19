"""Reprojection module for geospatial rasters using Rasterio and PyProj."""

from pathlib import Path
from typing import Optional, Union
import numpy as np
import rasterio
from rasterio.warp import Resampling, calculate_default_transform, reproject
from src.utils.logger import setup_logger

logger = setup_logger("reproject")


def reproject_raster(
    input_raster_path: Union[str, Path],
    output_raster_path: Union[str, Path],
    target_epsg: int = 32643,
    resampling_method: Resampling = Resampling.bilinear,
) -> Path:
    """Reprojects a GeoTIFF from its native CRS (e.g. EPSG:4326) to a target projected CRS

    (e.g. UTM Zone 43N EPSG:32643), re-evaluating affine transforms and grid dimensions.
    """
    input_p = Path(input_raster_path)
    out_p = Path(output_raster_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    dst_crs = f"EPSG:{target_epsg}"

    with rasterio.open(input_p) as src:
        src_crs = src.crs
        logger.info(f"Reprojecting {input_p.name} from {src_crs} to {dst_crs}")

        # If already matching, copy directly
        if str(src_crs).upper() == dst_crs.upper():
            logger.info("Source and target CRS match. Direct copy.")
            with rasterio.open(out_p, "w", **src.profile) as dst:
                dst.write(src.read())
            return out_p

        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds
        )

        kwargs = src.meta.copy()
        kwargs.update(
            {
                "crs": dst_crs,
                "transform": transform,
                "width": width,
                "height": height,
            }
        )

        with rasterio.open(out_p, "w", **kwargs) as dst:
            for band_idx in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, band_idx),
                    destination=rasterio.band(dst, band_idx),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=dst_crs,
                    resampling=resampling_method,
                )

    logger.info(f"Successfully reprojected raster saved to {out_p.name}")
    return out_p
