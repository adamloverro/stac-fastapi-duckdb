"""Base storage backend abstract class."""

from abc import ABC, abstractmethod
from typing import Optional


class StorageBackend(ABC):
    """Abstract base class for storage backends.
    
    Storage backends provide an abstraction for accessing files from different
    storage systems (local filesystem, Azure Blob Storage, S3, etc.).
    
    For cloud storage, the backend is responsible for authentication and
    providing DuckDB-compatible URLs that can be used with DuckDB's httpfs
    or other extensions.
    """

    @abstractmethod
    def get_url(self, path: str) -> str:
        """Get a DuckDB-compatible URL for the given path.
        
        This method transforms a storage path into a URL that DuckDB can read from.
        
        Args:
            path: The path to the file in the storage backend.
                  For local files, this is a filesystem path.
                  For cloud storage, this may be a relative path within a container/bucket.
        
        Returns:
            A URL that DuckDB can use to read the file. This may include:
            - file:// URLs for local files
            - https:// URLs with SAS tokens for Azure Blob Storage
            - s3:// URLs for S3
            - Any other URL scheme supported by DuckDB extensions
        
        Examples:
            Local: "data/file.parquet" -> "file:///path/to/data/file.parquet"
            Azure: "file.parquet" -> "https://account.blob.core.windows.net/container/file.parquet?sas_token"
        """
        pass

    @abstractmethod
    def validate_connection(self) -> bool:
        """Validate that the storage backend is properly configured and accessible.
        
        Returns:
            True if the connection is valid, False otherwise.
        
        Raises:
            Exception: If validation fails with a specific error.
        """
        pass

    def get_storage_type(self) -> str:
        """Get the type of storage backend.
        
        Returns:
            A string identifier for the storage type.
            
        Note:
            Subclasses should override this method to provide an explicit type identifier.
            The default implementation derives it from the class name, which may be fragile.
        """
        return self.__class__.__name__.replace("StorageBackend", "").lower()
