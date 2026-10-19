"""Unit and integration tests for loading modules (COG converter, DB Loader, File Manager)."""

import pytest
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from src.load.cog_converter import convert_to_cog
from src.load.file_manager import FileManager
from src.api.models import BoundingBoxQuery, SpatialRadiusQuery, RasterMetadataResponse


def test_file_manager_hierarchy(tmp_path):
    """Tests file hierarchy generation and sha256 calculation."""
    fm = FileManager(raw_dir=tmp_path / "raw", processed_dir=tmp_path / "processed")
    target_path = fm.generate_processed_path(scene_id="S2_TEST_123", product_name="NDVI")

    assert "NDVI.tif" in target_path.name
    assert "S2_TEST_123" in target_path.name

    # Write dummy file and check hash
    target_path.write_text("geospatial test payload")
    checksum = fm.compute_sha256(target_path)
    assert len(checksum) == 64


def test_cog_conversion_and_validation(tmp_path):
    """Tests that a standard GeoTIFF is converted to a valid tiled COG."""
    input_tif = tmp_path / "source.tif"
    width, height = 256, 256
    transform = from_bounds(77.5, 12.9, 77.7, 13.1, width, height)
    data = np.random.uniform(0.0, 1.0, (height, width)).astype(np.float32)

    with rasterio.open(
        input_tif, "w", driver="GTiff", height=height, width=width, count=1,
        dtype="float32", crs="EPSG:4326", transform=transform, nodata=np.nan
    ) as dst:
        dst.write(data, 1)

    output_cog = tmp_path / "source_cog.tif"
    convert_to_cog(input_tif, output_cog, profile_name="deflate")

    assert output_cog.exists()

    # Verify tiling
    with rasterio.open(output_cog) as src:
        assert src.is_tiled is True
        assert src.block_shapes[0] == (256, 256)


def test_api_schema_validations():
    """Validates Pydantic schema validation for spatial queries."""
    # Valid Bbox
    bbox = BoundingBoxQuery(min_lon=77.0, min_lat=12.0, max_lon=78.0, max_lat=13.0)
    assert bbox.min_lon == 77.0

    # Invalid Lat/Lon boundary
    with pytest.raises(Exception):
        BoundingBoxQuery(min_lon=200.0, min_lat=12.0, max_lon=78.0, max_lat=13.0)

    # Valid Radius
    query = SpatialRadiusQuery(latitude=13.0, longitude=77.5, radius_km=30.0)
    assert query.radius_km == 30.0
