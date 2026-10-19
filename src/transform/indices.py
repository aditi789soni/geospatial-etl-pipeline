"""Spectral index calculations for remote sensing imagery (NDVI, NDWI).

Performs vectorized floating-point calculations with numerical stability safeguards
and zero-division suppression.
"""

from pathlib import Path
from typing import Dict, Tuple, Union
import numpy as np
import rasterio
from src.utils.logger import setup_logger

logger = setup_logger("indices")


def calculate_ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    """Calculates Normalized Difference Vegetation Index (NDVI).

    NDVI = (NIR - Red) / (NIR + Red)
    Valid output values range from -1.0 to 1.0.
    """
    nir_f = nir.astype(np.float32)
    red_f = red.astype(np.float32)

    denominator = nir_f + red_f
    numerator = nir_f - red_f

    # Suppress divide-by-zero or NaN warning
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = np.where(denominator != 0, numerator / denominator, np.nan)

    # Clean extreme floating point artifacts outside [-1, 1]
    ndvi = np.where((ndvi >= -1.0) & (ndvi <= 1.0), ndvi, np.nan)
    return ndvi.astype(np.float32)


def calculate_ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Calculates Normalized Difference Water Index (NDWI) (McFeeters).

    NDWI = (Green - NIR) / (Green + NIR)
    Valid output values range from -1.0 to 1.0.
    """
    green_f = green.astype(np.float32)
    nir_f = nir.astype(np.float32)

    denominator = green_f + nir_f
    numerator = green_f - nir_f

    with np.errstate(divide="ignore", invalid="ignore"):
        ndwi = np.where(denominator != 0, numerator / denominator, np.nan)

    ndwi = np.where((ndwi >= -1.0) & (ndwi <= 1.0), ndwi, np.nan)
    return ndwi.astype(np.float32)


def compute_raster_ndvi_file(
    nir_path: Union[str, Path],
    red_path: Union[str, Path],
    output_ndvi_path: Union[str, Path],
) -> Tuple[Path, Dict[str, float]]:
    """Reads NIR (B8) and Red (B4) GeoTIFFs, computes NDVI, writes result

    to output GeoTIFF, and returns summary statistical metrics.
    """
    nir_p = Path(nir_path)
    red_p = Path(red_path)
    out_p = Path(output_ndvi_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(nir_p) as nir_src, rasterio.open(red_p) as red_src:
        nir_data = nir_src.read(1)
        red_data = red_src.read(1)
        profile = nir_src.profile.copy()

    ndvi_data = calculate_ndvi(nir_data, red_data)

    profile.update(
        dtype=rasterio.float32,
        count=1,
        nodata=np.nan,
    )

    with rasterio.open(out_p, "w", **profile) as dst:
        dst.write(ndvi_data, 1)

    valid_mask = ~np.isnan(ndvi_data)
    valid_pixels = ndvi_data[valid_mask]

    stats = {
        "min": float(np.min(valid_pixels)) if valid_pixels.size > 0 else 0.0,
        "max": float(np.max(valid_pixels)) if valid_pixels.size > 0 else 0.0,
        "mean": float(np.mean(valid_pixels)) if valid_pixels.size > 0 else 0.0,
        "std": float(np.std(valid_pixels)) if valid_pixels.size > 0 else 0.0,
        "valid_percentage": float((valid_pixels.size / ndvi_data.size) * 100.0),
    }

    logger.info(f"NDVI computed -> Mean: {stats['mean']:.4f}, Valid Px: {stats['valid_percentage']:.1f}%")
    return out_p, stats
