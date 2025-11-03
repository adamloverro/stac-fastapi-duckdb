"""Tests for DuckDB configuration with storage backends."""

import importlib.util

import pytest

from stac_fastapi.duckdb.config import DuckDBSettings
from stac_fastapi.duckdb.storage import LocalStorageBackend

# Check if Azure dependencies are available
try:
    AZURE_AVAILABLE = importlib.util.find_spec("azure.storage.blob") is not None
except (ImportError, ModuleNotFoundError):
    AZURE_AVAILABLE = False


class TestDuckDBSettingsWithStorage:
    """Tests for DuckDBSettings storage integration."""

    def test_default_settings_use_local_storage(self, tmp_path):
        """Test that default settings create a local storage backend."""
        settings = DuckDBSettings(
            stac_file_path=str(tmp_path),
            parquet_urls_json='{"test": "data/file.parquet"}',
        )
        assert settings.storage_type == "local"
        assert isinstance(settings.storage_backend, LocalStorageBackend)

    def test_get_collection_parquet_url_with_local_backend(self, tmp_path):
        """Test URL resolution with local storage backend."""
        settings = DuckDBSettings(
            stac_file_path=str(tmp_path),
            storage_type="local",
            parquet_urls_json='{"test": "data/file.parquet"}',
        )
        url = settings.get_collection_parquet_url("test")
        assert url.startswith("file://")
        assert "data/file.parquet" in url

    def test_get_collection_parquet_url_with_file_scheme(self, tmp_path):
        """Test that file:// URLs are preserved for backward compatibility."""
        settings = DuckDBSettings(
            stac_file_path=str(tmp_path),
            storage_type="local",
            parquet_urls_json='{"test": "file:///absolute/path/file.parquet"}',
        )
        url = settings.get_collection_parquet_url("test")
        assert url == "file:///absolute/path/file.parquet"

    def test_get_collection_parquet_url_with_http_scheme(self, tmp_path):
        """Test that http:// URLs are preserved for backward compatibility."""
        settings = DuckDBSettings(
            stac_file_path=str(tmp_path),
            storage_type="local",
            parquet_urls_json='{"test": "http://example.com/file.parquet"}',
        )
        url = settings.get_collection_parquet_url("test")
        assert url == "http://example.com/file.parquet"

    def test_get_collection_parquet_url_with_https_scheme(self, tmp_path):
        """Test that https:// URLs are preserved for backward compatibility."""
        settings = DuckDBSettings(
            stac_file_path=str(tmp_path),
            storage_type="local",
            parquet_urls_json='{"test": "https://example.com/file.parquet"}',
        )
        url = settings.get_collection_parquet_url("test")
        assert url == "https://example.com/file.parquet"

    def test_get_collection_parquet_url_with_s3_scheme(self, tmp_path):
        """Test that s3:// URLs are preserved for backward compatibility."""
        settings = DuckDBSettings(
            stac_file_path=str(tmp_path),
            storage_type="local",
            parquet_urls_json='{"test": "s3://bucket/file.parquet"}',
        )
        url = settings.get_collection_parquet_url("test")
        assert url == "s3://bucket/file.parquet"

    def test_resolve_sources_with_storage_backend(self, tmp_path):
        """Test that resolve_sources uses storage backend."""
        settings = DuckDBSettings(
            stac_file_path=str(tmp_path),
            storage_type="local",
            parquet_urls_json='{"coll1": "data/file1.parquet", "coll2": "data/file2.parquet"}',
        )
        sources = settings.resolve_sources(["coll1", "coll2"])
        assert len(sources) == 2
        assert sources[0][0] == "coll1"
        assert sources[1][0] == "coll2"
        # Both URLs should be transformed to file:// scheme
        assert sources[0][1].startswith("file://")
        assert sources[1][1].startswith("file://")

    @pytest.mark.skipif(not AZURE_AVAILABLE, reason="Azure dependencies not installed")
    def test_azure_storage_configuration(self, tmp_path):
        """Test Azure storage backend configuration."""
        settings = DuckDBSettings(
            stac_file_path=str(tmp_path),
            storage_type="azure_blob",
            azure_account_name="testaccount",
            azure_container_name="testcontainer",
            azure_authentication="sas_token",
            azure_sas_token="sv=2022-11-02&ss=b&srt=co&sp=r",
            parquet_urls_json='{"test": "data/file.parquet"}',
        )
        assert settings.storage_type == "azure_blob"
        assert settings.storage_backend.get_storage_type() == "azure_blob"

    def test_missing_collection_raises_error(self, tmp_path):
        """Test that missing collection raises ValueError."""
        settings = DuckDBSettings(
            stac_file_path=str(tmp_path),
            parquet_urls_json='{"test": "data/file.parquet"}',
        )
        with pytest.raises(ValueError, match="No Parquet URL configured"):
            settings.get_collection_parquet_url("nonexistent")
