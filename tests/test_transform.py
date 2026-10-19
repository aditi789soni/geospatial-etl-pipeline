"""Unit tests for raster transformation modules (Cloud mask, NDVI, Reproject, Clip, QA)."""

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds
from shapely.geometry import box
from src.transform.cloud_mask import apply_cloud_mask_to_band, create_cloud_mask_from_scl
from src.transform.indices import calculate_ndvi, calculate_ndwi
from src.transform.reproject import reproject_raster
from src.transform.clip import clip_raster_with_geometry
from src.transform.quality_check import validate_ndvi_quality, RasterQualityError


def test_ndvi_vectorized_calculation():
    """Tests NDVI formula and edge cases."""
    nir = np.array([4000, 3000, 1000, 0], dtype=np.uint16)
    red = np.array([1000, 1000, 3000, 0], dtype=np.uint16)

    ndvi = calculate_ndvi(nir, red)

    # (4000 - 1000) / (4000 + 1000) = 3000 / 5000 = 0.6
    assert pytest.approx(ndvi[0], 0.001) == 0.6
    # (3000 - 1000) / (3000 + 1000) = 2000 / 4000 = 0.5
    assert pytest.approx(ndvi[1], 0.001) == 0.5
    # (1000 - 3000) / (1000 + 3000) = -2000 / 4000 = -0.5
    assert pytest.approx(ndvi[2], 0.001) == -0.5
    # Zero denominator should resolve to NaN without crashing
    assert np.isnan(ndvi[3])


def test_ndwi_vectorized_calculation():
    """Tests NDWI formula (Green - NIR) / (Green + NIR)."""
    green = np.array([3000, 1000], dtype=np.uint16)
    nir = np.array([1000, 3000], dtype=np.uint16)

    ndwi = calculate_ndwi(green, nir)
    assert pytest.approx(ndwi[0], 0.001) == 0.5
    assert pytest.approx(ndwi[1], 0.001) == -0.5


def test_cloud_mask_from_scl():
    """Tests that SCL cloud and shadow classes (3, 8, 9) are masked."""
    scl = np.array([[4, 4], [9, 3]], dtype=np.uint8)
    mask = create_cloud_mask_from_scl(scl)

    assert not mask[0, 0]  # Vegetation (4) -> False (keep)
    assert not mask[0, 1]  # Vegetation (4) -> False (keep)
    assert mask[1, 0]      # Cloud High Prob (9) -> True (mask)
    assert mask[1, 1]      # Cloud Shadow (3) -> True (mask)

    band = np.array([[1500, 1600], [2000, 1800]], dtype=np.float32)
    masked_band = apply_cloud_mask_to_band(band, mask, nodata_value=np.nan)
    assert not np.isnan(masked_band[0, 0])
    assert np.isnan(masked_band[1, 0])


def test_reprojection_and_clipping(tmp_path):
    """Creates a sample GeoTIFF and tests CRS reprojection and spatial clipping."""
    # 1. Create a dummy raster in EPSG:4326
    raw_tif = tmp_path / "test_raw.tif"
    width, height = 50, 50
    transform = from_bounds(77.5, 12.9, 77.7, 13.1, width, height)
    data = np.ones((height, width), dtype=np.float32) * 0.4

    with rasterio.open(
        raw_tif,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=np.nan,
    ) as dst:
        dst.write(data, 1)

    # 2. Reproject to UTM Zone 43N (EPSG:32643)
    utm_tif = tmp_path / "test_utm.tif"
    reproject_raster(raw_tif, utm_tif, target_epsg=32643)

    with rasterio.open(utm_tif) as src:
        assert src.crs.to_epsg() == 32643

    # 3. Clip with geometry
    clip_tif = tmp_path / "test_clip.tif"
    clip_poly = box(77.55, 12.95, 77.65, 13.05)
    clip_raster_with_geometry(raw_tif, clip_tif, geometries=[clip_poly])

    assert clip_tif.exists()
    with rasterio.open(clip_tif) as src:
        assert src.width < width
        assert src.height < height


def test_quality_check_validation(tmp_path):
    """Tests the QA validation checks on valid and out-of-bound rasters."""
    valid_tif = tmp_path / "valid_ndvi.tif"
    width, height = 20, 20
    transform = from_bounds(77.5, 12.9, 77.7, 13.1, width, height)
    valid_data = np.random.uniform(0.1, 0.8, (height, width)).astype(np.float32)

    with rasterio.open(
        valid_tif, "w", driver="GTiff", height=height, width=width, count=1,
        dtype="float32", crs="EPSG:4326", transform=transform, nodata=np.nan
    ) as dst:
        dst.write(valid_data, 1)

    report = validate_ndvi_quality(valid_tif, min_valid_pct=50.0)
    assert report["passed"] is True
    assert report["status"] == "PASSED"

    # Test out-of-range failure
    invalid_tif = tmp_path / "invalid_ndvi.tif"
    bad_data = np.ones((height, width), dtype=np.float32) * 2.5
    with rasterio.open(
        invalid_tif, "w", driver="GTiff", height=height, width=width, count=1,
        dtype="float32", crs="EPSG:4326", transform=transform, nodata=np.nan
    ) as dst:
        dst.write(bad_data, 1)

    with pytest.raises(RasterQualityError):
        validate_ndvi_quality(invalid_tif)
