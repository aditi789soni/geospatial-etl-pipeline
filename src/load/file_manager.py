"""File management utility for organizing, archiving, and indexing processed rasters."""

import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union
from src.utils.config import settings
from src.utils.logger import setup_logger

logger = setup_logger("file_manager")


class FileManager:
    """Manages raw and processed geospatial data directories, naming conventions,

    checksum hashing, and archiving.
    """

    def __init__(
        self,
        raw_dir: Optional[Union[str, Path]] = None,
        processed_dir: Optional[Union[str, Path]] = None,
    ):
        self.raw_dir = Path(raw_dir or settings.RAW_DATA_DIR)
        self.processed_dir = Path(processed_dir or settings.PROCESSED_DATA_DIR)

        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def generate_processed_path(
        self,
        scene_id: str,
        product_name: str,
        extension: str = "tif",
        date: Optional[datetime] = None,
    ) -> Path:
        """Constructs a deterministic directory hierarchy:

        data/processed/<YYYY>/<MM>/<scene_id>_<product_name>.<ext>
        """
        date_ref = date or datetime.utcnow()
        year_str = date_ref.strftime("%Y")
        month_str = date_ref.strftime("%m")

        target_dir = self.processed_dir / year_str / month_str
        target_dir.mkdir(parents=True, exist_ok=True)

        clean_scene_id = scene_id.replace("/", "_").replace(":", "_")
        filename = f"{clean_scene_id}_{product_name}.{extension}"
        return target_dir / filename

    @staticmethod
    def compute_sha256(file_path: Union[str, Path]) -> str:
        """Calculates SHA256 checksum for artifact integrity verification."""
        path = Path(file_path)
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                sha256.update(block)
        return sha256.hexdigest()

    def list_processed_cogs(self) -> List[Path]:
        """Returns all generated Cloud Optimized GeoTIFF files."""
        return sorted(list(self.processed_dir.glob("**/*_cog.tif")))

    def clean_temporary_files(self, prefix: str = "temp_") -> int:
        """Removes intermediate pipeline files."""
        deleted_count = 0
        for temp_file in self.processed_dir.glob(f"**/{prefix}*"):
            try:
                if temp_file.is_file():
                    temp_file.unlink()
                    deleted_count += 1
            except Exception as exc:
                logger.warning(f"Could not delete temp file {temp_file}: {exc}")
        logger.info(f"Cleaned {deleted_count} temporary files.")
        return deleted_count


file_manager = FileManager()
