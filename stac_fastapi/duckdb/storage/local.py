"""Local filesystem storage backend."""

import logging
import os
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from stac_fastapi.duckdb.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class LocalStorageBackend(StorageBackend):
    """Storage backend for local filesystem access.
    
    This backend handles local file access and provides file:// URLs for DuckDB.
    It maintains backward compatibility with the existing local file support.
    """

    def __init__(self, base_path: Optional[str] = None):
        """Initialize the local storage backend.
        
        Args:
            base_path: Optional base directory for relative paths.
                      If not provided, paths are assumed to be absolute.
        """
        self.base_path = Path(base_path) if base_path else None
        logger.info(f"Initialized LocalStorageBackend with base_path: {base_path}")

    def get_url(self, path: str) -> str:
        """Get a file:// URL for a local file path.
        
        Args:
            path: Local filesystem path. Can be:
                  - Absolute path: /path/to/file.parquet
                  - Relative path: data/file.parquet (uses base_path if set)
                  - file:// URL: file:///path/to/file.parquet (returned as-is)
        
        Returns:
            A file:// URL that DuckDB can read.
        
        Examples:
            "/data/file.parquet" -> "file:///data/file.parquet"
            "file:///data/file.parquet" -> "file:///data/file.parquet"
            "data/file.parquet" (with base_path="/home") -> "file:///home/data/file.parquet"
        """
        # If already a file:// URL, return as-is
        if path.startswith("file://"):
            return path

        # Convert to Path for normalization
        path_obj = Path(path)

        # Make absolute if relative and base_path is set
        if not path_obj.is_absolute() and self.base_path:
            path_obj = self.base_path / path_obj

        # Convert to absolute path
        abs_path = path_obj.resolve()

        # Return file:// URL
        # Use quote to handle special characters in path
        return f"file://{abs_path}"

    def validate_connection(self) -> bool:
        """Validate local storage access.
        
        For local storage, this checks if the base_path exists and is accessible.
        
        Returns:
            True if validation succeeds.
        
        Raises:
            ValueError: If base_path is set but doesn't exist or isn't a directory.
        """
        if self.base_path:
            if not self.base_path.exists():
                raise ValueError(f"Base path does not exist: {self.base_path}")
            if not self.base_path.is_dir():
                raise ValueError(f"Base path is not a directory: {self.base_path}")
            logger.info(f"Local storage validated: {self.base_path}")
        else:
            logger.info("Local storage validated (no base path)")
        return True

    def get_storage_type(self) -> str:
        """Get the storage type identifier."""
        return "local"
