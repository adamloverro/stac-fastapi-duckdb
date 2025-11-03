"""Tests for storage backends."""
import importlib.util
from pathlib import Path

import pytest

from stac_fastapi.duckdb.storage import LocalStorageBackend, get_storage_backend
from stac_fastapi.duckdb.storage.base import StorageBackend

# Check if Azure dependencies are available
try:
    AZURE_AVAILABLE = importlib.util.find_spec('azure.storage.blob') is not None
except (ImportError, ModuleNotFoundError):
    AZURE_AVAILABLE = False


class TestLocalStorageBackend:
    """Tests for LocalStorageBackend."""

    def test_local_backend_creation(self):
        """Test creating a local storage backend."""
        backend = LocalStorageBackend()
        assert isinstance(backend, StorageBackend)
        assert backend.get_storage_type() == "local"

    def test_local_backend_with_base_path(self, tmp_path):
        """Test local backend with a base path."""
        backend = LocalStorageBackend(base_path=str(tmp_path))
        assert backend.base_path == tmp_path

    def test_get_url_absolute_path(self):
        """Test get_url with absolute path."""
        backend = LocalStorageBackend()
        url = backend.get_url("/data/file.parquet")
        assert url.startswith("file://")
        assert url.endswith("data/file.parquet")

    def test_get_url_relative_path_with_base(self, tmp_path):
        """Test get_url with relative path and base path."""
        backend = LocalStorageBackend(base_path=str(tmp_path))
        url = backend.get_url("data/file.parquet")
        assert url.startswith("file://")
        assert str(tmp_path) in url
        assert url.endswith("data/file.parquet")

    def test_get_url_file_scheme_passthrough(self):
        """Test that file:// URLs are passed through unchanged."""
        backend = LocalStorageBackend()
        input_url = "file:///data/file.parquet"
        output_url = backend.get_url(input_url)
        assert output_url == input_url

    def test_validate_connection_no_base_path(self):
        """Test validation succeeds with no base path."""
        backend = LocalStorageBackend()
        assert backend.validate_connection() is True

    def test_validate_connection_with_valid_base_path(self, tmp_path):
        """Test validation succeeds with valid base path."""
        backend = LocalStorageBackend(base_path=str(tmp_path))
        assert backend.validate_connection() is True

    def test_validate_connection_with_invalid_base_path(self):
        """Test validation fails with non-existent base path."""
        backend = LocalStorageBackend(base_path="/nonexistent/path")
        with pytest.raises(ValueError, match="Base path does not exist"):
            backend.validate_connection()

    def test_validate_connection_with_file_as_base_path(self, tmp_path):
        """Test validation fails when base path is a file."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("test")
        backend = LocalStorageBackend(base_path=str(file_path))
        with pytest.raises(ValueError, match="Base path is not a directory"):
            backend.validate_connection()


class TestStorageFactory:
    """Tests for storage backend factory."""

    def test_get_local_backend(self):
        """Test factory creates local backend."""
        backend = get_storage_backend(storage_type="local")
        assert isinstance(backend, LocalStorageBackend)

    def test_get_local_backend_with_path(self, tmp_path):
        """Test factory creates local backend with base path."""
        backend = get_storage_backend(
            storage_type="local",
            local_data_path=str(tmp_path)
        )
        assert isinstance(backend, LocalStorageBackend)
        assert backend.base_path == tmp_path

    def test_unsupported_storage_type(self):
        """Test factory raises error for unsupported type."""
        with pytest.raises(ValueError, match="Unsupported storage type"):
            get_storage_backend(storage_type="unsupported")

    def test_s3_not_implemented(self):
        """Test S3 backend raises not implemented error."""
        with pytest.raises(ValueError, match="not yet implemented"):
            get_storage_backend(storage_type="s3")


class TestAzureBlobStorageBackend:
    """Tests for AzureBlobStorageBackend."""

    def test_azure_backend_requires_dependencies(self):
        """Test that Azure backend factory handles missing dependencies."""
        if AZURE_AVAILABLE:
            pytest.skip("Azure dependencies are installed")
        # When dependencies are not available, the factory should raise ImportError
        with pytest.raises(ImportError, match="Azure storage dependencies not installed"):
            get_storage_backend(
                storage_type="azure_blob",
                azure_account_name="testaccount",
                azure_container_name="testcontainer"
            )

    def test_azure_backend_creation_requires_account_name(self):
        """Test Azure backend creation requires account name."""
        with pytest.raises(ValueError, match="azure_account_name is required"):
            get_storage_backend(
                storage_type="azure_blob",
                azure_container_name="test-container"
            )

    def test_azure_backend_creation_requires_container_name(self):
        """Test Azure backend creation requires container name."""
        with pytest.raises(ValueError, match="azure_container_name is required"):
            get_storage_backend(
                storage_type="azure_blob",
                azure_account_name="testaccount"
            )

    @pytest.mark.skipif(not AZURE_AVAILABLE, reason="Azure dependencies not installed")
    def test_azure_backend_creation_with_managed_identity(self):
        """Test Azure backend creation with managed identity."""
        from stac_fastapi.duckdb.storage.azure import AzureBlobStorageBackend
        
        backend = AzureBlobStorageBackend(
            account_name="testaccount",
            container_name="testcontainer",
            authentication="managed_identity"
        )
        assert backend.account_name == "testaccount"
        assert backend.container_name == "testcontainer"
        assert backend.authentication == "managed_identity"
        assert backend.get_storage_type() == "azure_blob"

    @pytest.mark.skipif(not AZURE_AVAILABLE, reason="Azure dependencies not installed")
    def test_azure_backend_get_url_without_sas(self):
        """Test Azure backend URL generation without SAS token."""
        from stac_fastapi.duckdb.storage.azure import AzureBlobStorageBackend
        
        backend = AzureBlobStorageBackend(
            account_name="testaccount",
            container_name="testcontainer",
            authentication="managed_identity"
        )
        url = backend.get_url("path/to/file.parquet")
        expected = "https://testaccount.blob.core.windows.net/testcontainer/path/to/file.parquet"
        assert url == expected

    @pytest.mark.skipif(not AZURE_AVAILABLE, reason="Azure dependencies not installed")
    def test_azure_backend_get_url_with_sas(self):
        """Test Azure backend URL generation with SAS token."""
        from stac_fastapi.duckdb.storage.azure import AzureBlobStorageBackend
        
        sas_token = "sv=2022-11-02&ss=b&srt=co&sp=r&se=2024-12-31"
        backend = AzureBlobStorageBackend(
            account_name="testaccount",
            container_name="testcontainer",
            authentication="sas_token",
            sas_token=sas_token
        )
        url = backend.get_url("path/to/file.parquet")
        assert url.startswith("https://testaccount.blob.core.windows.net/testcontainer/path/to/file.parquet")
        assert "sv=2022-11-02" in url

    @pytest.mark.skipif(not AZURE_AVAILABLE, reason="Azure dependencies not installed")
    def test_azure_backend_requires_sas_token_for_sas_auth(self):
        """Test Azure backend requires SAS token when using SAS authentication."""
        from stac_fastapi.duckdb.storage.azure import AzureBlobStorageBackend
        
        with pytest.raises(ValueError, match="sas_token is required"):
            AzureBlobStorageBackend(
                account_name="testaccount",
                container_name="testcontainer",
                authentication="sas_token"
            )

    @pytest.mark.skipif(not AZURE_AVAILABLE, reason="Azure dependencies not installed")
    def test_azure_backend_requires_connection_string_for_conn_auth(self):
        """Test Azure backend requires connection string for connection string authentication."""
        from stac_fastapi.duckdb.storage.azure import AzureBlobStorageBackend
        
        with pytest.raises(ValueError, match="connection_string is required"):
            AzureBlobStorageBackend(
                account_name="testaccount",
                container_name="testcontainer",
                authentication="connection_string"
            )
