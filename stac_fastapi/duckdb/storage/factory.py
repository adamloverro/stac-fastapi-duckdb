"""Factory for creating storage backend instances."""

import logging
from typing import Optional

from stac_fastapi.duckdb.storage.base import StorageBackend
from stac_fastapi.duckdb.storage.local import LocalStorageBackend

logger = logging.getLogger(__name__)


def get_storage_backend(
    storage_type: str = "local",
    # Local storage settings
    local_data_path: Optional[str] = None,
    # Azure storage settings
    azure_account_name: Optional[str] = None,
    azure_container_name: Optional[str] = None,
    azure_authentication: str = "managed_identity",
    azure_connection_string: Optional[str] = None,
    azure_sas_token: Optional[str] = None,
) -> StorageBackend:
    """Create storage backend instances.

    Args:
        storage_type: Type of storage backend to create ("local", "azure_blob", "s3").
        local_data_path: Base path for local storage (optional).
        azure_account_name: Azure storage account name.
        azure_container_name: Azure blob container name.
        azure_authentication: Azure authentication method.
        azure_connection_string: Azure connection string.
        azure_sas_token: Azure SAS token.

    Returns:
        Configured StorageBackend instance.

    Raises:
        ValueError: If storage_type is unsupported or required parameters are missing.
    """
    storage_type = storage_type.lower()

    if storage_type == "local":
        logger.info("Creating LocalStorageBackend")
        return LocalStorageBackend(base_path=local_data_path)

    elif storage_type == "azure_blob":
        try:
            from stac_fastapi.duckdb.storage.azure import AzureBlobStorageBackend
        except ImportError as e:
            raise ImportError(
                "Azure storage backend requires additional dependencies. "
                "Install with: pip install azure-storage-blob azure-identity adlfs"
            ) from e

        if not azure_account_name:
            raise ValueError("azure_account_name is required for Azure Blob Storage")
        if not azure_container_name:
            raise ValueError("azure_container_name is required for Azure Blob Storage")

        logger.info(
            f"Creating AzureBlobStorageBackend for {azure_account_name}/{azure_container_name}"
        )
        return AzureBlobStorageBackend(
            account_name=azure_account_name,
            container_name=azure_container_name,
            authentication=azure_authentication,
            connection_string=azure_connection_string,
            sas_token=azure_sas_token,
        )

    elif storage_type == "s3":
        # S3 support can be added in the future
        raise ValueError(
            "S3 storage backend is not yet implemented. "
            "Supported backends: local, azure_blob"
        )

    else:
        raise ValueError(
            f"Unsupported storage type: {storage_type}. "
            f"Supported types: local, azure_blob"
        )
