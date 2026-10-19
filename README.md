# Geospatial ETL Pipeline

Production-grade, automated Earth Observation (EO) satellite processing pipeline designed for ingesting Sentinel-2 imagery, computing cloud-masked vegetation & water indices (NDVI/NDWI), reprojecting across CRS projections, generating Cloud Optimized GeoTIFFs (COGs), indexing footprints in PostGIS, and serving spatial queries via FastAPI.

---

## 1. System Architecture

```
+----------------------------------------------------------------------------------------+
|                                    DATA EXTRACTION                                     |
|  Google Earth Engine (GEE API)  /  Copernicus SciHub  /  Open-Meteo REST Weather API   |
+----------------------------------------------------------------------------------------+
                                           |
                                           v [Raw GeoTIFFs: B2, B3, B4, B8, SCL]
+----------------------------------------------------------------------------------------+
|                                   TRANSFORMATION                                       |
|  1. Pixel-Level Cloud Masking (Scene Classification Layer - SCL)                       |
|  2. Vectorized Spectral Band Math:                                                     |
|       NDVI = (NIR - Red) / (NIR + Red)                                                 |
|       NDWI = (Green - NIR) / (Green + NIR)                                             |
|  3. Spatial Reprojection (WGS84 EPSG:4326 -> UTM Zone 43N EPSG:32643 via Rasterio)      |
|  4. Polygon Boundary Vector Masking & Spatial Clipping (GeoPandas / Shapely)           |
+----------------------------------------------------------------------------------------+
                                           |
                                           v
+----------------------------------------------------------------------------------------+
|                                 QUALITY ASSURANCE                                      |
|  1. Valid Spectral Bounds Validation ([-1.0, 1.0])                                     |
|  2. Missing/NaN Density Threshold Checking (> 5% valid pixels)                         |
|  3. Signal Variance / Non-flat Surface Verification                                    |
+----------------------------------------------------------------------------------------+
                                           |
                                           v
+----------------------------------------------------------------------------------------+
|                                     LOADING                                            |
|  1. Cloud-Optimized GeoTIFF (COG) Translation & Overviews (rio-cogeo)                   |
|  2. Hierarchical File Storage Indexing (data/processed/YYYY/MM/)                       |
|  3. PostGIS Ingestion (GeoAlchemy2 ST_Polygon footprints with GiST Spatial Indexes)     |
+----------------------------------------------------------------------------------------+
                                           |
                    +----------------------+----------------------+
                    |                                             |
                    v                                             v
+---------------------------------------+     +---------------------------------------+
|             ORCHESTRATION             |     |              API SERVICE              |
|      Apache Airflow TaskFlow DAG      |     |       FastAPI Geospatial Search       |
| (Extract -> Transform -> Load -> Run) |     |  (Centroid Radius, PostGIS ST_DWithin)|
+---------------------------------------+     +---------------------------------------+
```

---

## 2. Technology Stack

| Layer | Component | Version / Tools | Purpose |
|---|---|---|---|
| **Language** | Python | 3.10+ | Core language environment |
| **Extraction** | Earth Engine API / Sentinelsat | `earthengine-api`, `sentinelsat` | Sentinel-2 L2A Harmonized retrieval |
| **Weather** | Open-Meteo | `requests` | Auxiliary atmospheric telemetry |
| **Raster Processing** | Rasterio, NumPy, PyProj | `rasterio`, `numpy`, `pyproj` | Vectorized math, reprojection, cloud masking |
| **Vector Geometry** | GeoPandas, Shapely | `geopandas`, `shapely` | CRS transformations, clipping polygons |
| **Cloud Storage** | Rio-Cogeo | `rio-cogeo` | Internal tiling, pyramids, COG generation |
| **Database** | PostgreSQL + PostGIS | `psycopg2-binary`, `geoalchemy2` | Spatial indexing, GiST indices, polygon bounding |
| **Orchestration** | Apache Airflow | `apache-airflow` | TaskFlow scheduling, DAG retry loops |
| **API** | FastAPI + Uvicorn | `fastapi`, `uvicorn`, `pydantic` | Spatial REST API endpoints |
| **Testing** | Pytest | `pytest` | Unit tests for raster math and APIs |

---

## 3. Directory Layout

```
geospatial-etl-pipeline/
├── data/
│   ├── raw/                      # Downloaded source Sentinel-2 bands
│   └── processed/                # Production Cloud-Optimized GeoTIFFs
├── dags/
│   └── satellite_etl_dag.py      # Apache Airflow orchestration DAG
├── docker/
│   ├── Dockerfile                # Multi-stage C++/GDAL/Python runtime
│   └── docker-compose.yml        # PostGIS, Airflow, and FastAPI multi-container
├── src/
│   ├── api/
│   │   ├── main.py               # FastAPI app with CORS middleware
│   │   ├── models.py             # Pydantic spatial query schemas
│   │   └── routes.py             # PostGIS ST_DWithin search endpoints
│   ├── extract/
│   │   ├── gee_downloader.py     # Earth Engine Sentinel-2 downloader
│   │   ├── sentinel_api.py       # Copernicus SciHub fallback
│   │   └── weather_api.py        # Open-Meteo auxiliary atmospheric client
│   ├── load/
│   │   ├── cog_converter.py      # COG conversion & validation via rio-cogeo
│   │   ├── db_loader.py          # SQLAlchemy / GeoAlchemy2 PostGIS models
│   │   └── file_manager.py       # Deterministic YYYY/MM artifact structure
│   ├── transform/
│   │   ├── clip.py               # Vector clipping against Shapely Polygons
│   │   ├── cloud_mask.py         # SCL pixel-level cloud & shadow masking
│   │   ├── indices.py            # Vectorized NDVI and NDWI calculations
│   │   ├── quality_check.py      # Range bounds and NaN threshold assurance
│   │   └── reproject.py          # GDAL/Rasterio CRS reprojection
│   └── utils/
│       ├── config.py             # Pydantic-settings environment configuration
│       ├── geo_utils.py          # Bounding box & UTM EPSG helpers
│       └── logger.py             # Structured logging setup
├── tests/
│   ├── test_extract.py           # Extraction tests
│   ├── test_transform.py         # Band math and reprojection tests
│   └── test_load.py              # COG and database tests
├── .gitignore
├── requirements.txt
├── run_pipeline.py               # Standalone pipeline CLI runner
└── README.md
```

---

## 4. Setup & Execution Guide

### Option A: Local Development Setup

1. **Clone & Virtual Environment**:
   ```bash
   cd geospatial-etl-pipeline
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configuration (`.env`)**:
   Create a `.env` file in the project root:
   ```env
   ENVIRONMENT=development
   LOG_LEVEL=INFO
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=postgres
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   POSTGRES_DB=geospatial_db
   DEFAULT_EPSG=32643
   MAX_CLOUD_COVER=20.0
   ```

3. **Run Full Pipeline via CLI**:
   Execute the entire ETL pipeline locally:
   ```bash
   python run_pipeline.py --min-lon 77.50 --min-lat 12.90 --max-lon 77.75 --max-lat 13.10 --epsg 32643
   ```

4. **Launch the FastAPI Server**:
   ```bash
   uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
   ```
   Interactive Swagger docs are accessible at: `http://localhost:8000/docs`

5. **Run the Test Suite**:
   ```bash
   pytest tests/ -v
   ```

---

### Option B: Docker Compose Deployment

Run the complete production stack (PostGIS + FastAPI + Airflow Webserver + Airflow Scheduler):

```bash
docker compose -f docker/docker-compose.yml up --build -d
```

- **FastAPI Documentation**: `http://localhost:8000/docs`
- **Airflow Web UI**: `http://localhost:8080` (Credentials: `admin` / `admin`)
- **PostGIS Port**: `localhost:5432`

---

## 5. API Reference & cURL Examples

### 1. Spatial Image Search by Lat/Lon & Radius
Returns scenes intersecting the radius buffer around a coordinate using PostGIS `ST_DWithin`:

```bash
curl -X GET "http://localhost:8000/api/v1/images?lat=13.00&lon=77.60&radius_km=30.0" \
     -H "Accept: application/json"
```

**Response**:
```json
[
  {
    "id": 1,
    "scene_id": "COPERNICUS/S2_SR_HARMONIZED/20230615T052651_T43REQ",
    "satellite_name": "Sentinel-2",
    "acquisition_date": "2023-06-15T05:26:51",
    "cloud_cover_pct": 8.5,
    "epsg_crs": 32643,
    "processed_cog_path": "data/processed/2023/06/COPERNICUS_S2_SR_HARMONIZED_20230615T052651_T43REQ_NDVI_COG.tif",
    "ndvi_mean": 0.5234,
    "ndvi_min": -0.0821,
    "ndvi_max": 0.892,
    "temperature_celsius": 26.4,
    "created_at": "2026-10-19T13:45:00"
  }
]
```

### 2. Trigger On-Demand Pipeline Run
```bash
curl -X POST "http://localhost:8000/api/v1/pipeline/trigger" \
     -H "Content-Type: application/json" \
     -d '{
       "min_lon": 77.50,
       "min_lat": 12.90,
       "max_lon": 77.75,
       "max_lat": 13.10,
       "start_date": "2023-06-01",
       "end_date": "2023-06-30",
       "target_epsg": 32643
     }'
```

---

## 6. PostGIS Spatial Query Examples

Connect to PostgreSQL using `psql` or DBeaver:

```sql
-- 1. Verify Spatial Reference & PostGIS Extension
SELECT PostGIS_Full_Version();

-- 2. Find all scenes intersecting a specific bounding polygon
SELECT scene_id, cloud_cover_pct, ndvi_mean, processed_cog_path
FROM satellite_raster_metadata
WHERE ST_Intersects(
    footprint,
    ST_MakeEnvelope(77.5, 12.9, 77.7, 13.1, 4326)
);

-- 3. Find all scenes within a 20 km buffer of Bangalore (EPSG:4326 transformed to metric EPSG:3857)
SELECT id, scene_id, acquisition_date, ndvi_mean,
       ROUND(ST_Distance(ST_Transform(footprint, 3857), ST_Transform(ST_SetSRID(ST_MakePoint(77.5946, 12.9716), 4326), 3857)) / 1000.0, 2) AS distance_km
FROM satellite_raster_metadata
WHERE ST_DWithin(
    ST_Transform(footprint, 3857),
    ST_Transform(ST_SetSRID(ST_MakePoint(77.5946, 12.9716), 4326), 3857),
    20000 -- 20 kilometers
)
ORDER BY acquisition_date DESC;

-- 4. Calculate spatial area in square kilometers for each indexed tile
SELECT scene_id,
       ROUND((ST_Area(ST_Transform(footprint, 3857)) / 1000000.0)::numeric, 2) AS area_sq_km
FROM satellite_raster_metadata;
```
