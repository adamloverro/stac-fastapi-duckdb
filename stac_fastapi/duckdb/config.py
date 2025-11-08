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
    azure_authentication: str = os.getenv(
        "STAC_STORAGE_AZURE_AUTHENTICATION", "managed_identity"
    )
    azure_connection_string: Optional[str] = os.getenv(
        "STAC_STORAGE_AZURE_CONNECTION_STRING"
    )
    azure_sas_token: Optional[str] = os.getenv("STAC_STORAGE_AZURE_SAS_TOKEN")
    azure_managed_identity_client_id: Optional[str] = os.getenv(
        "STAC_STORAGE_AZURE_MANAGED_IDENTITY_CLIENT_ID"
    )

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
            azure_managed_identity_client_id=self.azure_managed_identity_client_id,
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

        # Handle file:// URLs - convert to plain path and process through storage backend
        if configured_path.startswith("file://"):
            # Remove file:// prefix and convert to path
            # Handle both file://path and file:///path formats
            path_without_scheme = configured_path[7:]  # Remove "file://"
            if path_without_scheme.startswith("/"):
                # file:///absolute/path -> /absolute/path
                plain_path = path_without_scheme
            else:
                # file://./relative/path -> ./relative/path
                plain_path = path_without_scheme
            # Process through storage backend to get proper file:/// URL
            return self.storage_backend.get_url(plain_path)

        # If already a complete URL (http://, https://, s3://), return as-is
        if any(
            configured_path.startswith(scheme)
            for scheme in ["http://", "https://", "s3://"]
        ):
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

            # Configure authentication for httpfs if using credential & token
            # based access, e.g. azure managed identity
            self._configure_authentication(conn)

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

    def _configure_authentication(self, conn):
        """Configure DuckDB connection for https authentication.

        This method configures httpfs extension settings for authentication
        when using token based credentials, e.g. azure managed identity.
        For SAS token and connection string authentication,
        the authentication is handled via the URL parameters.

        Args:
            conn: DuckDB connection object
        """
        # Only configure authentication for Azure storage backend with managed identity
        if (
            self.storage_type == "azure_blob"
            and self.azure_authentication == "managed_identity"
        ):

            try:
                # Import Azure dependencies
                from azure.identity import (
                    DefaultAzureCredential,
                    ManagedIdentityCredential,
                )

                # Create credential instance matching the storage backend configuration
                credential = None
                storage_scope = "https://storage.azure.com/.default"

                if self.azure_managed_identity_client_id:
                    try:
                        logger.info(
                            f"Using managed identity with client ID: {self.azure_managed_identity_client_id}"
                        )

                        credential = ManagedIdentityCredential(
                            client_id=self.azure_managed_identity_client_id
                        )
                        logger.info(
                            "Successfully created ManagedIdentityCredential with client ID"
                        )
                        # Try to retrieve a token to validate the credential
                        token_response = credential.get_token(storage_scope)
                        logger.info(
                            "Successfully retrieved access token using managed identity client ID"
                        )
                    except RuntimeError as e:
                        logger.warning(
                            f"Managed identity with client ID {self.azure_managed_identity_client_id} is not available: {e}"
                        )
                        credential = None

                    except Exception as e:
                        logger.warning(
                            f"Failed to create credential from managed identity with client ID: {e}"
                        )
                        credential = None

                # Fall back to DefaultAzureCredential if specific client ID failed or not provided
                if credential is None:
                    try:
                        credential = DefaultAzureCredential()
                        logger.info(
                            "Using DefaultAzureCredential for DuckDB authentication"
                        )
                        # Retrieve access token
                        token_response = credential.get_token(storage_scope)
                        logger.info(
                            "Successfully retrieved access token using DefaultAzureCredential"
                        )
                    except Exception as e:
                        raise RuntimeError(
                            f"Failed to create DefaultAzureCredential: {e}"
                        )

                access_token = token_response.token

                # Configure DuckDB httpfs to use Bearer token authentication
                # TODO: Consider using DuckDB's native 'azure' extension instead of httpfs with manual authentication.
                # This would allow using: INSTALL azure; LOAD azure; and configuring via SET azure_storage_connection_string.
                # If the 'azure' extension does not support managed identity, clarify why the current httpfs approach is preferred.
                # For now, we set a secret with the Authorization header.
                conn.execute(
                    f"""CREATE SECRET http_auth (
                        TYPE http, 
                        EXTRA_HTTP_HEADERS MAP {{
                            'Authorization': 'Bearer {access_token}',
                            'x-ms-version': '2025-11-05'
                        }}
                    );"""
                )
                # Alternative approach if the above doesn't work:
                # Set HTTP headers for Azure blob requests
                # This is discouraged for security reasons, but shown here for completeness
                # conn.execute(f"SET http_timeout = 30000;")
                # conn.execute(f"SET http_keep_alive = true;")
                # conn.execute(f"SET http_custom_headers = 'Authorization=Bearer {access_token}';")

                logger.info(
                    "Successfully configured DuckDB with Azure managed identity token"
                )

            except ImportError:
                logger.warning(
                    "Azure identity dependencies not available. "
                    "Install with: pip install azure-identity"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to configure Azure authentication for DuckDB: {str(e)}"
                )
                logger.warning(
                    "DuckDB may not be able to access Azure Blob Storage without authentication"
                )
