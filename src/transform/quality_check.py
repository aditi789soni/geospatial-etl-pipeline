"""Quality check and validation module for transformed raster products."""

from pathlib import Path
from typing import Dict, Tuple, Union
import numpy as np
import rasterio
from src.utils.logger import setup_logger

logger = setup_logger("quality_check")


class RasterQualityError(Exception):
    """Raised when a geospatial product fails critical quality assurance checks."""
    pass


def validate_ndvi_quality(
    raster_path: Union[str, Path],
    min_valid_pct: float = 10.0,
    expected_range: Tuple[float, float] = (-1.0, 1.0),
) -> Dict[str, Union[bool, float, str]]:
    """Runs data sanity and integrity checks on an NDVI GeoTIFF:

    1. Checks that values fall strictly within the expected physical bounds [-1.0, 1.0].
    2. Validates that missing/NaN/nodata pixel percentage does not exceed the allowed threshold.
    3. Confirms non-zero standard deviation (not a flat blank image).
    """
    path = Path(raster_path)
    if not path.exists():
        raise FileNotFoundError(f"Raster file not found: {path}")

    with rasterio.open(path) as src:
        data = src.read(1)
        nodata = src.nodata

    total_pixels = data.size
    nan_mask = np.isnan(data)
    if nodata is not None:
        nan_mask = nan_mask | (data == nodata)

    valid_pixels = data[~nan_mask]
    valid_count = valid_pixels.size
    valid_pct = (valid_count / total_pixels) * 100.0

    if valid_count == 0:
        logger.error(f"Quality Check Failed for {path.name}: 100% missing or NaN values.")
        raise RasterQualityError("Raster contains no valid pixels.")

    p_min = float(np.min(valid_pixels))
    p_max = float(np.max(valid_pixels))
    p_mean = float(np.mean(valid_pixels))
    p_std = float(np.std(valid_pixels))

    # Range check
    is_range_valid = (p_min >= expected_range[0] - 1e-4) and (p_max <= expected_range[1] + 1e-4)
    # Valid coverage check
    is_coverage_valid = valid_pct >= min_valid_pct
    # Signal variance check
    is_signal_valid = p_std > 1e-6

    passed = is_range_valid and is_coverage_valid and is_signal_valid

    report = {
        "file": path.name,
        "passed": passed,
        "valid_pct": round(valid_pct, 2),
        "min_value": round(p_min, 4),
        "max_value": round(p_max, 4),
        "mean_value": round(p_mean, 4),
        "std_dev": round(p_std, 4),
        "status": "PASSED" if passed else "FAILED",
    }

    if not passed:
        logger.warning(f"Raster quality verification issue in {path.name}: {report}")
        if not is_coverage_valid:
            raise RasterQualityError(f"Valid pixel percentage {valid_pct:.1f}% below minimum threshold {min_valid_pct}%.")
        if not is_range_valid:
            raise RasterQualityError(f"Pixel values [{p_min}, {p_max}] outside allowable range {expected_range}.")
    else:
        logger.info(f"Quality check passed for {path.name}: {report}")

    return report
