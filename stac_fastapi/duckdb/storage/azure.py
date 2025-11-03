"""Azure Blob Storage backend."""

import logging
from typing import Optional
from urllib.parse import quote

from stac_fastapi.duckdb.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class AzureBlobStorageBackend(StorageBackend):
    """Storage backend for Azure Blob Storage.
    
    This backend provides access to GeoParquet files stored in Azure Blob Storage.
    It supports multiple authentication methods:
    - Managed Identity (DefaultAzureCredential)
    - SAS Token
    - Connection String
    
    The backend generates HTTPS URLs that DuckDB can read using its httpfs extension.
    """

    def __init__(
        self,
        account_name: str,
        container_name: str,
        authentication: str = "managed_identity",
        connection_string: Optional[str] = None,
        sas_token: Optional[str] = None,
    ):
        """Initialize Azure Blob Storage backend.
        
        Args:
            account_name: Azure storage account name.
            container_name: Azure blob container name.
            authentication: Authentication method. One of:
                           - "managed_identity": Use Azure Managed Identity (default)
                           - "sas_token": Use a SAS token
                           - "connection_string": Use a connection string
            connection_string: Azure storage connection string (if authentication="connection_string").
            sas_token: SAS token for authentication (if authentication="sas_token").
        
        Raises:
            ValueError: If required authentication parameters are missing.
            ImportError: If Azure SDK dependencies are not installed.
        """
        try:
            from azure.identity import DefaultAzureCredential
            from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
            from datetime import datetime, timedelta
        except ImportError as e:
            raise ImportError(
                "Azure storage dependencies not installed. "
                "Install with: pip install azure-storage-blob azure-identity adlfs"
            ) from e

        self.account_name = account_name
        self.container_name = container_name
        self.authentication = authentication
        self.connection_string = connection_string
        self.sas_token = sas_token
        self._blob_service_client: Optional[BlobServiceClient] = None

        # Validate authentication configuration
        if authentication == "connection_string" and not connection_string:
            raise ValueError("connection_string is required when authentication='connection_string'")
        if authentication == "sas_token" and not sas_token:
            raise ValueError("sas_token is required when authentication='sas_token'")

        logger.info(
            f"Initialized AzureBlobStorageBackend for account={account_name}, "
            f"container={container_name}, auth={authentication}"
        )

    def _get_blob_service_client(self):
        """Get or create a BlobServiceClient instance.
        
        Returns:
            BlobServiceClient instance configured with appropriate authentication.
        """
        if self._blob_service_client is not None:
            return self._blob_service_client

        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        if self.authentication == "connection_string":
            self._blob_service_client = BlobServiceClient.from_connection_string(
                self.connection_string
            )
        elif self.authentication == "sas_token":
            account_url = f"https://{self.account_name}.blob.core.windows.net"
            # SAS token should not have leading '?'
            sas_token = self.sas_token.lstrip("?") if self.sas_token else ""
            self._blob_service_client = BlobServiceClient(
                account_url=account_url,
                credential=sas_token
            )
        else:  # managed_identity
            account_url = f"https://{self.account_name}.blob.core.windows.net"
            credential = DefaultAzureCredential()
            self._blob_service_client = BlobServiceClient(
                account_url=account_url,
                credential=credential
            )

        return self._blob_service_client

    def get_url(self, path: str) -> str:
        """Get an HTTPS URL for Azure Blob Storage that DuckDB can read.
        
        Args:
            path: Path to the blob within the container (e.g., "data/file.parquet").
                  Should not include the container name.
        
        Returns:
            HTTPS URL with authentication parameters that DuckDB can use.
        
        Examples:
            With SAS token:
                "data/file.parquet" -> 
                "https://account.blob.core.windows.net/container/data/file.parquet?sas_token"
            
            With managed identity:
                "data/file.parquet" -> 
                "https://account.blob.core.windows.net/container/data/file.parquet"
                (Note: Managed identity requires additional DuckDB configuration)
        """
        # Remove leading slash if present
        path = path.lstrip("/")

        # URL encode the blob path
        encoded_path = quote(path, safe="/")

        # Base URL
        base_url = f"https://{self.account_name}.blob.core.windows.net/{self.container_name}/{encoded_path}"

        # Add SAS token if using SAS authentication
        if self.authentication == "sas_token" and self.sas_token:
            # Ensure token starts with '?' for URL
            token = self.sas_token if self.sas_token.startswith("?") else f"?{self.sas_token}"
            return f"{base_url}{token}"

        # For managed identity and connection string, return the base URL
        # Note: DuckDB's httpfs extension may need additional configuration for managed identity
        return base_url

    def validate_connection(self) -> bool:
        """Validate Azure Blob Storage connection.
        
        This attempts to connect to the storage account and verify the container exists.
        
        Returns:
            True if connection and container access succeed.
        
        Raises:
            Exception: If connection fails or container doesn't exist.
        """
        try:
            client = self._get_blob_service_client()
            container_client = client.get_container_client(self.container_name)
            
            # Try to get container properties to verify access
            container_client.get_container_properties()
            
            logger.info(
                f"Azure Blob Storage connection validated: "
                f"account={self.account_name}, container={self.container_name}"
            )
            return True
        except Exception as e:
            logger.error(f"Azure Blob Storage connection validation failed: {str(e)}")
            raise

    def get_storage_type(self) -> str:
        """Get the storage type identifier."""
        return "azure_blob"
