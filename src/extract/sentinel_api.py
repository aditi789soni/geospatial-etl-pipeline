"""Sentinel Hub and Copernicus Open Access Hub (sentinelsat) extraction client."""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
from src.utils.config import settings
from src.utils.logger import setup_logger

logger = setup_logger("sentinel_api")


class SentinelAPIClient:
    """Fallback client to search and extract Sentinel-2 products directly

    from the Copernicus SciHub or Sentinel Hub REST APIs.
    """

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.username = username or settings.COPERNICUS_USERNAME
        self.password = password or settings.COPERNICUS_PASSWORD
        self._init_api()

    def _init_api(self) -> None:
        """Initializes SentinelAPI connection if credentials are configured."""
        self.api = None
        if not self.username or not self.password:
            logger.info("Copernicus credentials not provided. Sentinelsat running in simulation mode.")
            return

        try:
            from sentinelsat import SentinelAPI
            self.api = SentinelAPI(
                self.username,
                self.password,
                "https://apihub.copernicus.eu/apihub",
            )
            logger.info("Copernicus SentinelAPI initialized successfully.")
        except Exception as exc:
            logger.warning(f"Could not connect to Copernicus Hub: {exc}. Using fallback.")

    def query_products(
        self,
        geojson_polygon: str,
        start_date: str,
        end_date: str,
        cloud_max_pct: float = 20.0,
    ) -> List[Dict]:
        """Queries Copernicus data catalog for Sentinel-2 Level-2A products."""
        if self.api is None:
            logger.info("Simulation mode: Querying Sentinel-2 catalog via Sentinelsat stub.")
            return [
                {
                    "title": "S2B_MSIL2A_20230615T052651_N0509_R019_T43REQ_20230615T084804",
                    "id": "e6749969-5282-4974-958b-944a1796d10c",
                    "cloudcoverpercentage": 11.2,
                    "date": "2023-06-15",
                    "size": "1.02 GB",
                }
            ]

        try:
            products = self.api.query(
                geojson_polygon,
                date=(start_date, end_date),
                platformname="Sentinel-2",
                processinglevel="Level-2A",
                cloudcoverpercentage=(0, cloud_max_pct),
            )
            logger.info(f"Retrieved {len(products)} products from Copernicus SciHub.")
            results = []
            for k, v in products.items():
                results.append(
                    {
                        "id": k,
                        "title": v.get("title"),
                        "cloudcoverpercentage": v.get("cloudcoverpercentage"),
                        "date": str(v.get("beginposition")),
                        "size": v.get("size"),
                    }
                )
            return results
        except Exception as exc:
            logger.error(f"Error querying Copernicus API: {exc}")
            return []

    def download_product(self, product_id: str, download_dir: Optional[Path] = None) -> Path:
        """Downloads full or partial SAFE package for given Sentinel product ID."""
        target_dir = Path(download_dir or settings.RAW_DATA_DIR)
        target_dir.mkdir(parents=True, exist_ok=True)
        out_file = target_dir / f"{product_id}.zip"

        if self.api is None:
            logger.info(f"Simulating download of product {product_id} to {out_file}")
            out_file.touch(exist_ok=True)
            return out_file

        try:
            self.api.download(product_id, directory_path=str(target_dir))
            logger.info(f"Downloaded product {product_id} to {target_dir}")
            return out_file
        except Exception as exc:
            logger.error(f"Failed to download product {product_id}: {exc}")
            raise
