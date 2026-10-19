"""Geospatial geometric and CRS helper utilities."""

import math
from typing import Dict, List, Tuple
from pyproj import CRS, Transformer
from shapely.geometry import Polygon, box, mapping


def bbox_to_polygon(minx: float, miny: float, maxx: float, maxy: float) -> Polygon:
    """Creates a Shapely Polygon from bounding box coordinates [minx, miny, maxx, maxy]."""
    return box(minx, miny, maxx, maxy)


def polygon_to_geojson(geom: Polygon) -> Dict:
    """Converts a Shapely geometry to a GeoJSON geometry dictionary."""
    return mapping(geom)


def point_radius_to_bbox(
    lat: float, lon: float, radius_km: float
) -> Tuple[float, float, float, float]:
    """Calculates approximate [min_lon, min_lat, max_lon, max_lat] bounding box

    given a centroid lat/lon and search radius in kilometers.
    """
    # 1 degree of latitude ~= 111.32 km
    lat_delta = radius_km / 111.32
    # 1 degree of longitude ~= 111.32 * cos(lat) km
    lon_delta = radius_km / (111.32 * math.cos(math.radians(lat)))

    min_lat = max(-90.0, lat - lat_delta)
    max_lat = min(90.0, lat + lat_delta)
    min_lon = max(-180.0, lon - lon_delta)
    max_lon = min(180.0, lon + lon_delta)

    return (min_lon, min_lat, max_lon, max_lat)


def get_utm_epsg_for_lon_lat(lon: float, lat: float) -> int:
    """Calculates the best-fit UTM zone EPSG code for a given WGS84 coordinate.

    Northern hemisphere: 32600 + zone, Southern: 32700 + zone.
    """
    zone_number = int((lon + 180) // 6) + 1
    if lat >= 0:
        return 32600 + zone_number
    return 32700 + zone_number


def transform_bounds(
    bounds: Tuple[float, float, float, float], src_epsg: int, dst_epsg: int
) -> Tuple[float, float, float, float]:
    """Transforms bounding box coordinates [minx, miny, maxx, maxy] between coordinate systems."""
    if src_epsg == dst_epsg:
        return bounds

    transformer = Transformer.from_crs(
        CRS.from_epsg(src_epsg), CRS.from_epsg(dst_epsg), always_xy=True
    )
    minx, miny, maxx, maxy = bounds
    t_minx, t_miny = transformer.transform(minx, miny)
    t_maxx, t_maxy = transformer.transform(maxx, maxy)
    return (t_minx, t_miny, t_maxx, t_maxy)


def validate_epsg(epsg_code: int) -> bool:
    """Validates if an integer corresponds to a recognized EPSG projection."""
    try:
        CRS.from_epsg(epsg_code)
        return True
    except Exception:
        return False
