"""FastAPI application entrypoint with middleware and lifecycle events."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import router as api_router
from src.load.db_loader import db_manager
from src.utils.config import settings
from src.utils.logger import setup_logger

logger = setup_logger("api_main")

app = FastAPI(
    title="Geospatial Satellite ETL & Imagery API",
    description="Production REST API for querying processed Sentinel-2 scenes, COGs, and NDVI statistics.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable Cross-Origin Resource Sharing (CORS) for web GIS clients (Leaflet, OpenLayers, Mapbox)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(api_router)


@app.on_event("startup")
def startup_event():
    """Initializes tables and confirms database accessibility on server boot."""
    logger.info("Initializing Geospatial API Server...")
    try:
        db_manager.init_db()
    except Exception as exc:
        logger.warning(f"Database initialization warning on startup: {exc}")


@app.get("/")
def root():
    """Root endpoint redirecting users to interactive Swagger documentation."""
    return {
        "service": "Geospatial Satellite ETL Pipeline API",
        "documentation": "/docs",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
