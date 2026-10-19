"""Cloud masking module for Sentinel-2 MSI data.

Applies pixel-level masking using the Scene Classification Layer (SCL)
or multi-band spectral thresholds.
"""

from pathlib import Path
from typing import Optional, Tuple, Union
import numpy as np
import rasterio
from src.utils.logger import setup_logger

logger = setup_logger("cloud_mask")

# Sentinel-2 SCL (Scene Classification Layer) classification classes:
# 0: NO_DATA, 1: SATURATED_OR_DEFECTIVE, 2: DARK_AREA_PIXELS, 3: CLOUD_SHADOWS
# 4: VEGETATION, 5: NOT_VEGETATED, 6: WATER, 7: UNCLASSIFIED, 8: CLOUD_MEDIUM_PROBABILITY
# 9: CLOUD_HIGH_PROBABILITY, 10: THIN_CIRRUS, 11: SNOW
INVALID_SCL_CLASSES = (0, 1, 3, 8, 9, 10)


def create_cloud_mask_from_scl(scl_array: np.ndarray) -> np.ndarray:
    """Creates a boolean mask where True indicates clouds, shadows, or invalid data.

    Input scl_array: 2D numpy array with Sentinel-2 SCL integer labels.
    Returns: 2D boolean array (True = Masked/Cloudy, False = Valid surface).
    """
    mask = np.isin(scl_array, INVALID_SCL_CLASSES)
    cloud_pct = (np.sum(mask) / mask.size) * 100.0
    logger.info(f"SCL Cloud Mask computed: {cloud_pct:.2f}% pixels classified as cloud/shadow/invalid.")
    return mask


def apply_cloud_mask_to_band(
    band_array: np.ndarray,
    mask: np.ndarray,
    nodata_value: float = np.nan,
) -> np.ndarray:
    """Applies the boolean cloud mask to a target reflectance band array.

    Pixels where mask == True are replaced with nodata_value.
    """
    masked_band = band_array.astype(np.float32).copy()
    masked_band[mask] = nodata_value
    return masked_band


def mask_raster_file(
    input_raster_path: Union[str, Path],
    scl_raster_path: Union[str, Path],
    output_raster_path: Union[str, Path],
) -> Path:
    """Reads a raster GeoTIFF and its corresponding SCL raster, generates

    a cloud-masked output GeoTIFF with nodata values preserved.
    """
    input_p = Path(input_raster_path)
    scl_p = Path(scl_raster_path)
    out_p = Path(output_raster_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(scl_p) as scl_src:
        scl_data = scl_src.read(1)

    cloud_mask = create_cloud_mask_from_scl(scl_data)

    with rasterio.open(input_p) as src:
        profile = src.profile.copy()
        band_data = src.read(1)

        profile.update(
            dtype=rasterio.float32,
            nodata=np.nan,
        )

        masked_data = apply_cloud_mask_to_band(band_data, cloud_mask, nodata_value=np.nan)

        with rasterio.open(out_p, "w", **profile) as dst:
            dst.write(masked_data, 1)

    logger.info(f"Successfully wrote cloud-masked raster to: {out_p.name}")
    return out_p
