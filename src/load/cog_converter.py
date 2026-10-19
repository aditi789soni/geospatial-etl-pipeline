"""Cloud Optimized GeoTIFF (COG) generation module using rio-cogeo."""

from pathlib import Path
from typing import Optional, Union
import rasterio
from rio_cogeo.cogeo import cog_translate, cog_validate
from rio_cogeo.profiles import cog_profiles
from src.utils.logger import setup_logger

logger = setup_logger("cog_converter")


def convert_to_cog(
    input_geotiff_path: Union[str, Path],
    output_cog_path: Union[str, Path],
    profile_name: str = "deflate",
    overview_resampling: str = "bilinear",
    web_optimized: bool = False,
) -> Path:
    """Converts a standard GeoTIFF into a Cloud-Optimized GeoTIFF (COG)

    with internal tiling (256x256), overviews, and lossless compression (Deflate or LZW).
    """
    in_p = Path(input_geotiff_path)
    out_p = Path(output_cog_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    if not in_p.exists():
        raise FileNotFoundError(f"Source GeoTIFF not found: {in_p}")

    dst_profile = cog_profiles.get(profile_name)

    # Configure profile options for optimal cloud streaming
    config = {
        "GDAL_NUM_THREADS": "ALL_CPUS",
        "GDAL_TIFF_INTERNAL_MASK": True,
        "GDAL_TIFF_OVR_BLOCKSIZE": "128",
    }

    logger.info(f"Converting {in_p.name} to Cloud Optimized GeoTIFF ({profile_name})...")

    cog_translate(
        in_p,
        out_p,
        dst_profile,
        config=config,
        overview_resampling=overview_resampling,
        web_optimized=web_optimized,
        quiet=True,
    )

    # Validate output compliance
    is_valid, errors, warnings = cog_validate(out_p)
    if not is_valid:
        logger.error(f"Generated file is not a valid COG: {errors}")
        raise ValueError(f"COG validation failed for {out_p.name}: {errors}")

    logger.info(f"Successfully generated and validated COG at: {out_p.name}")
    return out_p
