"""Storage abstraction for local and cloud storage backends."""

from stac_fastapi.duckdb.storage.base import StorageBackend
from stac_fastapi.duckdb.storage.factory import get_storage_backend
from stac_fastapi.duckdb.storage.local import LocalStorageBackend

__all__ = [
    "StorageBackend",
    "LocalStorageBackend",
    "get_storage_backend",
]

try:
    from stac_fastapi.duckdb.storage.azure import AzureBlobStorageBackend

    __all__.append("AzureBlobStorageBackend")
except ImportError:
    # Azure dependencies not installed
    pass
