"""Integration tests for Azure Blob Storage backend.

These tests require real Azure infrastructure and should only be run
when Azure test resources are available.

Environment variables required:
- AZURE_STORAGE_ACCOUNT: Azure storage account name
- AZURE_TEST_CONTAINER: Container name for testing
- AZURE_SAS_TOKEN: SAS token for authentication testing
- AZURE_CLIENT_ID: Managed identity client ID (for managed identity testing)
- AZURE_TENANT_ID: Azure tenant ID
- AZURE_SUBSCRIPTION_ID: Azure subscription ID

Usage:
    # Run integration tests with Azure resources
    make test-azure-integration

    # Skip integration tests (default behavior)
    pytest tests/ -v -m "not integration"
"""

import os

import pytest

from stac_fastapi.duckdb.storage import get_storage_backend
from stac_fastapi.duckdb.storage.azure import AzureBlobStorageBackend


@pytest.fixture
def azure_storage_account():
    """Get Azure storage account name from environment."""
    account = os.getenv("AZURE_STORAGE_ACCOUNT")
    if not account:
        pytest.skip("AZURE_STORAGE_ACCOUNT environment variable not set")
    return account


@pytest.fixture
def azure_test_container():
    """Get Azure test container name from environment."""
    container = os.getenv("AZURE_TEST_CONTAINER")
    if not container:
        pytest.skip("AZURE_TEST_CONTAINER environment variable not set")
    return container


@pytest.fixture
def azure_sas_token():
    """Get Azure SAS token from environment."""
    token = os.getenv("AZURE_SAS_TOKEN")
    if not token:
        pytest.skip("AZURE_SAS_TOKEN environment variable not set")
    return token


@pytest.fixture
def azure_managed_identity_client_id():
    """Get Azure managed identity client ID from environment."""
    client_id = os.getenv("AZURE_CLIENT_ID")
    if not client_id:
        pytest.skip("AZURE_CLIENT_ID environment variable not set")
    return client_id


class TestAzureIntegration:
    """Integration tests for Azure Blob Storage backend."""

    @pytest.mark.integration
    def test_azure_sas_token_connection(
        self, azure_storage_account, azure_test_container, azure_sas_token
    ):
        """Test real Azure connection using SAS token authentication."""
        backend = AzureBlobStorageBackend(
            account_name=azure_storage_account,
            container_name=azure_test_container,
            authentication="sas_token",
            sas_token=azure_sas_token,
        )

        # Test connection validation
        assert backend.validate_connection() is True

        # Test URL generation
        url = backend.get_url("test/file.parquet")
        assert azure_storage_account in url
        assert azure_test_container in url
        assert "test/file.parquet" in url
        assert azure_sas_token.lstrip("?") in url

    @pytest.mark.integration
    def test_azure_managed_identity_connection(
        self,
        azure_storage_account,
        azure_test_container,
        azure_managed_identity_client_id,
    ):
        """Test real Azure connection using managed identity authentication."""
        backend = AzureBlobStorageBackend(
            account_name=azure_storage_account,
            container_name=azure_test_container,
            authentication="managed_identity",
            managed_identity_client_id=azure_managed_identity_client_id,
        )

        # Test connection validation
        # Note: This will only work if running in an environment with managed identity access
        # (e.g., Azure VM, Azure Container Instance, etc.)
        try:
            assert backend.validate_connection() is True
        except Exception as e:
            # If we're not running in Azure environment with managed identity,
            # we expect authentication to fail
            if "authentication" in str(e).lower() or "credential" in str(e).lower():
                pytest.skip(f"Managed identity unavailable in current environment: {e}")
            else:
                raise

        # Test URL generation (should work regardless of auth environment)
        url = backend.get_url("test/file.parquet")
        assert azure_storage_account in url
        assert azure_test_container in url
        assert "test/file.parquet" in url
        # Managed identity URLs should not contain SAS tokens
        assert "?" not in url

    @pytest.mark.integration
    def test_azure_factory_with_sas_token(
        self, azure_storage_account, azure_test_container, azure_sas_token
    ):
        """Test Azure backend creation through factory with SAS token."""
        backend = get_storage_backend(
            storage_type="azure_blob",
            azure_account_name=azure_storage_account,
            azure_container_name=azure_test_container,
            azure_authentication="sas_token",
            azure_sas_token=azure_sas_token,
        )

        assert isinstance(backend, AzureBlobStorageBackend)
        assert backend.validate_connection() is True

    @pytest.mark.integration
    def test_azure_factory_with_managed_identity(
        self,
        azure_storage_account,
        azure_test_container,
        azure_managed_identity_client_id,
    ):
        """Test Azure backend creation through factory with managed identity."""
        backend = get_storage_backend(
            storage_type="azure_blob",
            azure_account_name=azure_storage_account,
            azure_container_name=azure_test_container,
            azure_authentication="managed_identity",
            azure_managed_identity_client_id=azure_managed_identity_client_id,
        )

        assert isinstance(backend, AzureBlobStorageBackend)

        # Test connection (with same managed identity caveat as above)
        try:
            assert backend.validate_connection() is True
        except Exception as e:
            if "authentication" in str(e).lower() or "credential" in str(e).lower():
                pytest.skip(f"Managed identity unavailable in current environment: {e}")
            else:
                raise

    @pytest.mark.integration
    def test_azure_url_accessibility(
        self, azure_storage_account, azure_test_container, azure_sas_token
    ):
        """Test that generated Azure URLs are actually accessible via HTTP."""
        import requests

        backend = AzureBlobStorageBackend(
            account_name=azure_storage_account,
            container_name=azure_test_container,
            authentication="sas_token",
            sas_token=azure_sas_token,
        )

        # Generate URL for a test file (we'll assume it doesn't exist)
        url = backend.get_url("nonexistent/test.parquet")

        # Make HTTP request to verify URL structure is correct
        # We expect either 404 (file not found) or 200 (file exists)
        # Any other error indicates URL formatting issues
        response = requests.head(url, timeout=30)

        # 404 is acceptable (file doesn't exist)
        # 200 is acceptable (file exists)
        # 403 might indicate permission issues
        assert response.status_code in [200, 404], (
            f"Unexpected status code {response.status_code}. "
            f"This might indicate URL formatting issues or permission problems."
        )

    @pytest.mark.integration
    def test_azure_duckdb_integration(
        self, azure_storage_account, azure_test_container, azure_sas_token
    ):
        """Test that DuckDB can actually read from Azure URLs generated by the backend."""
        import duckdb

        backend = AzureBlobStorageBackend(
            account_name=azure_storage_account,
            container_name=azure_test_container,
            authentication="sas_token",
            sas_token=azure_sas_token,
        )

        # Create a temporary DuckDB connection
        conn = duckdb.connect(":memory:")

        # Install and load httpfs extension for remote file access
        conn.execute("INSTALL httpfs;")
        conn.execute("LOAD httpfs;")

        # Generate URL for test file using real STAC collection data
        # The deployment script uploads real collection parquet files
        test_file_url = backend.get_url(
            "collections/io-lulc-9-class/io-lulc-9-class.parquet"
        )

        try:
            # Try to query the parquet file
            # This will fail if the file doesn't exist, but that's okay for now
            result = conn.execute(f"SELECT COUNT(*) FROM '{test_file_url}'").fetchone()
            if result:
                print(f"Successfully read from Azure: {result[0]} rows")
            else:
                print("Query returned no results")
        except Exception as e:
            # If file doesn't exist, that's expected
            if "No such file or directory" in str(e) or "HTTP Error 404" in str(e):
                pytest.skip(f"Test file missing in Azure container: {e}")
            else:
                # Other errors might indicate real connectivity issues
                pytest.fail(f"DuckDB failed to process Azure URL: {e}")
        finally:
            conn.close()


class TestAzureIntegrationErrorCases:
    """Test error cases with real Azure infrastructure."""

    @pytest.mark.integration
    def test_invalid_container_name(self, azure_storage_account, azure_sas_token):
        """Test connection failure with invalid container name."""
        backend = AzureBlobStorageBackend(
            account_name=azure_storage_account,
            container_name="nonexistent-container-12345",
            authentication="sas_token",
            sas_token=azure_sas_token,
        )

        with pytest.raises(Exception):
            backend.validate_connection()

    @pytest.mark.integration
    def test_invalid_sas_token(self, azure_storage_account, azure_test_container):
        """Test connection failure with invalid SAS token."""
        backend = AzureBlobStorageBackend(
            account_name=azure_storage_account,
            container_name=azure_test_container,
            authentication="sas_token",
            sas_token="invalid-sas-token",
        )

        with pytest.raises(Exception):
            backend.validate_connection()

    @pytest.mark.integration
    def test_invalid_storage_account(self, azure_test_container, azure_sas_token):
        """Test connection failure with invalid storage account."""
        backend = AzureBlobStorageBackend(
            account_name="nonexistentaccount12345",
            container_name=azure_test_container,
            authentication="sas_token",
            sas_token=azure_sas_token,
        )

        with pytest.raises(Exception):
            backend.validate_connection()
