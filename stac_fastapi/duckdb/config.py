"""DuckDB runtime configuration and data source mapping."""
import json
import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import duckdb
from stac_fastapi.core.base_settings import ApiBaseSettings

# from stac_fastapi.core.utilities import get_bool_env
from stac_fastapi.types.config import ApiSettings

from stac_fastapi.duckdb.storage import StorageBackend, get_storage_backend

logger = logging.getLogger(__name__)


class DuckDBSettings(ApiSettings, ApiBaseSettings):
    """DuckDB API settings and configuration."""

    # Core API settings
    forbidden_fields: Set[str] = {"id", "type", "collection"}
    indexed_fields: Set[str] = {
        "datetime",
        "start_datetime",
        "end_datetime",
        "geometry",
    }
    # enable_response_models: bool = False

    # DuckDB-specific settings
    stac_file_path: str = os.getenv("STAC_FILE_PATH", "/app/stac_collections")
    parquet_urls_json: str = os.getenv("PARQUET_URLS_JSON", "{}")
    duckdb_database_path: str = os.getenv(
        "DUCKDB_DATABASE_PATH", "/tmp/stac_fastapi.duckdb"
    )
    _parquet_urls: Dict[str, str] = {}

    # Storage backend settings
    storage_type: str = os.getenv("STAC_STORAGE_STORAGE_TYPE", "local")
    
    # Local storage settings
    local_data_path: Optional[str] = os.getenv("STAC_STORAGE_LOCAL_DATA_PATH")
    
    # Azure Blob Storage settings
    azure_account_name: Optional[str] = os.getenv("STAC_STORAGE_AZURE_ACCOUNT_NAME")
    azure_container_name: Optional[str] = os.getenv("STAC_STORAGE_AZURE_CONTAINER_NAME")
    azure_authentication: str = os.getenv("STAC_STORAGE_AZURE_AUTHENTICATION", "managed_identity")
    azure_connection_string: Optional[str] = os.getenv("STAC_STORAGE_AZURE_CONNECTION_STRING")
    azure_sas_token: Optional[str] = os.getenv("STAC_STORAGE_AZURE_SAS_TOKEN")
    
    _storage_backend: Optional[StorageBackend] = None

    def __init__(self, **data: Any) -> None:
        """Initialize the settings."""
        super().__init__(**data)
        self._parquet_urls = json.loads(self.parquet_urls_json)

        # Validate STAC file path if it's set and exists
        # Only log a warning if it doesn't exist (don't fail initialization)
        if self.stac_file_path and not os.path.isdir(self.stac_file_path):
            logger.warning(f"STAC file path does not exist: {self.stac_file_path}")
        
        # Initialize storage backend
        self._storage_backend = self._create_storage_backend()
        
        # Validate storage backend connection
        try:
            self._storage_backend.validate_connection()
        except Exception as e:
            logger.warning(f"Storage backend validation failed: {e}")
            # Don't fail initialization - allow runtime errors to surface later

    @property
    def parquet_urls(self) -> Dict[str, str]:
        """Get the configured Parquet URLs."""
        return self._parquet_urls

    @parquet_urls.setter
    def parquet_urls(self, value: Union[Dict[str, str], str]) -> None:
        """Set Parquet URLs from either a dict or JSON string."""
        if isinstance(value, str):
            self._parquet_urls = json.loads(value)
        else:
            self._parquet_urls = value

    @property
    def database_refresh(self) -> Union[bool, str]:
        """Get the refresh setting for database operations."""
        return None

    def create_client(self):
        """Create a synchronous DuckDB client."""
        # Import here to avoid circular imports
        from stac_fastapi.duckdb.database_logic import DuckDBClient

        return DuckDBClient(settings=self)
    
    def _create_storage_backend(self) -> StorageBackend:
        """Create and configure the storage backend.
        
        Returns:
            Configured StorageBackend instance.
        """
        return get_storage_backend(
            storage_type=self.storage_type,
            local_data_path=self.local_data_path,
            azure_account_name=self.azure_account_name,
            azure_container_name=self.azure_container_name,
            azure_authentication=self.azure_authentication,
            azure_connection_string=self.azure_connection_string,
            azure_sas_token=self.azure_sas_token,
        )
    
    @property
    def storage_backend(self) -> StorageBackend:
        """Get the storage backend instance."""
        if self._storage_backend is None:
            self._storage_backend = self._create_storage_backend()
        return self._storage_backend

    def get_collection_parquet_url(self, collection_id: str) -> str:
        """Get the Parquet URL for a collection.
        
        This method returns a DuckDB-compatible URL by:
        1. Looking up the configured path/URL for the collection
        2. Transforming it through the storage backend to get a DuckDB-readable URL
        
        Args:
            collection_id: The collection identifier.
        
        Returns:
            A DuckDB-compatible URL (file://, https://, s3://, etc.).
        """
        if collection_id not in self._parquet_urls:
            raise ValueError(
                f"No Parquet URL configured for collection: {collection_id}"
            )
        
        configured_path = self._parquet_urls[collection_id]
        
        # If the path is already a complete URL (http://, https://, s3://, etc.),
        # return it as-is for backward compatibility
        if any(configured_path.startswith(scheme) for scheme in ["http://", "https://", "s3://", "file://"]):
            return configured_path
        
        # Otherwise, transform through storage backend
        return self.storage_backend.get_url(configured_path)

    def get_collection_parquet_sources(
        self, collection_ids: Optional[list[str]] = None
    ) -> list[tuple[str, str]]:
        """Get a list of (collection_id, parquet_url) tuples.
        
        URLs are transformed through the storage backend to be DuckDB-compatible.
        """
        if not collection_ids:
            collection_ids = list(self._parquet_urls.keys())

        sources = []
        for cid in collection_ids:
            if cid not in self._parquet_urls:
                raise ValueError(f"No Parquet configured for collection '{cid}'")
            
            # Get the DuckDB-compatible URL through storage backend
            url = self.get_collection_parquet_url(cid)
            sources.append((cid, url))
        return sources

    def resolve_sources(
        self, collection_ids: Optional[List[str]] = None
    ) -> List[Tuple[str, str]]:
        """Resolve collection ids to (collection_id, parquet_url) pairs.

        Thin wrapper used by DatabaseLogic.
        """
        pairs = self.get_collection_parquet_sources(collection_ids)
        return [(cid, url) for cid, url in pairs]

    @contextmanager
    def create_connection(self):
        """Create a per-request DuckDB connection with httpfs and spatial extensions configured."""
        conn = duckdb.connect(database=self.duckdb_database_path)
        try:
            # Enable remote I/O via httpfs where available
            try:
                conn.execute("INSTALL httpfs;")
                logger.info("Successfully installed httpfs extension")
            except Exception as e:
                logger.warning(f"Failed to install httpfs extension: {str(e)}")

            try:
                conn.execute("LOAD httpfs;")
                logger.info("Successfully loaded httpfs extension")
            except Exception as e:
                logger.warning(f"Failed to load httpfs extension: {str(e)}")

            # Install and load spatial extension for geometry functions
            try:
                conn.execute("INSTALL spatial;")
                logger.info("Successfully installed spatial extension")
            except Exception as e:
                logger.warning(f"Failed to install spatial extension: {str(e)}")

            try:
                conn.execute("LOAD spatial;")
                logger.info("Successfully loaded spatial extension")
            except Exception as e:
                logger.error(f"Failed to load spatial extension: {str(e)}")
                logger.error(
                    "Spatial functions like ST_Intersects will not work without the spatial extension"
                )

            # Best-effort caching knobs
            try:
                # Enable object cache
                conn.execute("SET enable_object_cache=true")
                logger.info("Enabled object cache")

                # Enable parquet metadata cache
                try:
                    conn.execute("SET parquet_metadata_cache=true")
                    logger.info("Enabled parquet metadata cache")
                except Exception as e:
                    logger.warning(f"Could not enable parquet metadata cache: {str(e)}")
            except Exception as e:
                logger.warning(f"Failed to configure caching: {str(e)}")

            yield conn
        finally:
            try:
                conn.close()
            except Exception:
                pass
