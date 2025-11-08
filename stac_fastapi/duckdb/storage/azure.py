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
        managed_identity_client_id: Optional[str] = None,
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
            managed_identity_client_id: Client ID for managed identity authentication
                                       (optional, if not provided uses system-assigned identity).

        Raises:
            ValueError: If required authentication parameters are missing.
            ImportError: If Azure SDK dependencies are not installed.
        """
        try:
            from azure.storage.blob import BlobServiceClient  # noqa: F401
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
        self.managed_identity_client_id = managed_identity_client_id
        self._blob_service_client: Optional[BlobServiceClient] = None

        # Validate authentication configuration
        if authentication == "connection_string" and not connection_string:
            raise ValueError(
                "connection_string is required when authentication='connection_string'"
            )
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
            account_url = "https://" + self.account_name + ".blob.core.windows.net"
            # SAS token should not have leading '?'
            sas_token = self.sas_token.lstrip("?") if self.sas_token else ""
            self._blob_service_client = BlobServiceClient(
                account_url=account_url,
                credential=sas_token,
            )
        else:  # managed_identity
            account_url = "https://" + self.account_name + ".blob.core.windows.net"
            credential = None

            # First try to use specific managed identity client ID if provided
            if self.managed_identity_client_id:
                try:
                    from azure.identity import ManagedIdentityCredential

                    credential = ManagedIdentityCredential(
                        client_id=self.managed_identity_client_id
                    )

                    # Test credential availability before using it
                    self._validate_managed_identity_credential(credential)
                    logger.info(
                        f"Using managed identity with client ID: {self.managed_identity_client_id}"
                    )

                except RuntimeError as e:
                    logger.warning(
                        f"Managed identity with client ID {self.managed_identity_client_id} is not available: {e}. "
                        f"Runtime: Falling back to DefaultAzureCredential."
                    )
                    credential = None
                except Exception as e:
                    logger.warning(
                        f"Failed to create managed identity credential with client ID {self.managed_identity_client_id}: {e}. "
                        f"Exception: Falling back to DefaultAzureCredential."
                    )
                    credential = None

                # If no specific client ID or managed identity failed, try DefaultAzureCredential
                if credential is None:
                    try:
                        logger.info("Using DefaultAzureCredential for authentication")
                        credential = DefaultAzureCredential()
                        logger.info("DefaultAzureCredential created successfully")
                    except Exception as e:
                        raise RuntimeError(
                            f"Failed to create any valid Azure credential. "
                            f"Managed identity not available and DefaultAzureCredential failed: {e}"
                        ) from e

            self._blob_service_client = BlobServiceClient(
                account_url=account_url,
                credential=credential,
            )

        return self._blob_service_client

    def _validate_managed_identity_credential(self, credential) -> None:
        """Validate that the managed identity credential is available.

        This method attempts to get a token using the credential to verify
        that the managed identity is accessible in the current environment.

        Args:
            credential: Azure credential object to validate

        Raises:
            RuntimeError: If managed identity is not available in the current environment
        """
        try:
            # Try to get a token for Azure Storage scope
            # This will fail immediately if IMDS is not available
            credential.get_token("https://storage.azure.com/.default")
            logger.debug("Managed identity credential validated successfully")
        except Exception as e:
            error_msg = str(e)
            if (
                "IMDS endpoint" in error_msg
                or "ManagedIdentityCredential authentication unavailable" in error_msg
            ):
                raise RuntimeError(
                    "Managed identity authentication is not available in this environment. "
                    "This typically happens when running outside of Azure (e.g., locally). "
                    "Consider using SAS token authentication instead."
                ) from e
            else:
                # Re-raise other credential errors as-is
                raise

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
        base_url = (
            "https://"
            + self.account_name
            + ".blob.core.windows.net/"
            + self.container_name
            + "/"
            + encoded_path
        )

        # Add SAS token if using SAS authentication
        if self.authentication == "sas_token" and self.sas_token:
            # Ensure token starts with '?' for URL
            token = (
                self.sas_token
                if self.sas_token.startswith("?")
                else f"?{self.sas_token}"
            )
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

            # Try to list blobs to verify read/list access
            # This is less privileged than get_container_properties
            blob_list = container_client.list_blobs()
            # Just try to get the first item or confirm iterator works
            try:
                next(iter(blob_list))
            except StopIteration:
                # Empty container is fine, we just verified access
                pass

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
