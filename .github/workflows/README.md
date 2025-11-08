# GitHub Actions Configuration

This document describes the GitHub Actions workflow configuration for the stac-fastapi-duckdb project.

## Workflows

### Main CI/CD Pipeline (`cicd.yml`)

The main workflow runs on:
- Push to `main` branch
- Pull requests to `main` branch
- Pull requests to `features/**` branches

#### Jobs

##### 1. Test Job

Tests the application with multiple Python versions (3.9, 3.10, 3.11, 3.12) using a matrix strategy.

**Steps:**
1. **Checkout** - Gets the repository code
2. **Setup Python** - Installs the specified Python version
3. **Lint Code** - Runs pre-commit hooks (only on Python 3.12)
4. **Build Docker Image** - Builds the application container
5. **Run Test Suite** - Executes pytest with unit tests (excludes integration tests)

**Environment Variables for Docker Build:**
- `STAC_FILE_PATH`: Path to STAC collections directory
- `PARQUET_URLS_JSON`: Configuration for parquet file locations
- `STAC_STORAGE_STORAGE_TYPE`: Storage backend type (empty defaults to local)
- `STAC_STORAGE_AZURE_*`: Azure storage configuration (empty for local testing)
- `LOG_LEVEL`: Logging level

##### 2. Azure Integration Test Job (Optional)

This job runs only when Azure credentials are properly configured in the repository secrets and variables.

**Prerequisites:**
- Repository Variables:
  - `AZURE_RESOURCE_GROUP_NAME`: Name of the Azure resource group
  - `AZURE_LOCATION`: Azure region (defaults to 'eastus')
- Repository Secrets:
  - `AZURE_CREDENTIALS`: JSON credentials for Azure service principal
  - `AZURE_CLIENT_ID`: Azure service principal client ID
  - `AZURE_CLIENT_SECRET`: Azure service principal client secret
  - `AZURE_TENANT_ID`: Azure tenant ID

**Steps:**
1. **Checkout** - Gets the repository code
2. **Setup Python** - Installs Python 3.12
3. **Azure Login** - Authenticates with Azure using service principal
4. **Deploy Azure Infrastructure** - Runs the Azure deployment script
5. **Build Docker Image** - Builds with Azure storage configuration
6. **Run Azure Integration Tests** - Executes integration tests against Azure resources
7. **Cleanup Azure Resources** - Removes created resources (always runs)

## Setting Up Azure Integration Testing

To enable Azure integration testing in your fork or repository:

### 1. Create Azure Service Principal

```bash
az ad sp create-for-rbac --name "github-actions-stac-fastapi-duckdb" \
  --role contributor \
  --scopes /subscriptions/{subscription-id} \
  --sdk-auth
```

### 2. Configure Repository Secrets

In your GitHub repository settings, add the following secrets:

- `AZURE_CREDENTIALS`: The complete JSON output from the service principal creation
- `AZURE_CLIENT_ID`: The appId from the service principal
- `AZURE_CLIENT_SECRET`: The password from the service principal  
- `AZURE_TENANT_ID`: The tenant from the service principal

### 3. Configure Repository Variables

In your GitHub repository settings, add the following variables:

- `AZURE_RESOURCE_GROUP_NAME`: A unique name for your test resource group (e.g., "rg-stac-fastapi-test-{your-initials}")
- `AZURE_LOCATION`: The Azure region to use (optional, defaults to "eastus")

### 4. Verify Setup

Once configured, the Azure integration tests will run automatically on pushes and pull requests, deploying temporary Azure infrastructure, running tests, and cleaning up resources.

## Environment Variables Reference

### Standard Environment Variables
- `STAC_FILE_PATH`: Path to STAC collection files
- `PARQUET_URLS_JSON`: JSON mapping of collection names to parquet file URLs
- `LOG_LEVEL`: Application logging level (DEBUG, INFO, WARNING, ERROR)
- `ENVIRONMENT`: Runtime environment identifier

### Azure Storage Environment Variables
- `STAC_STORAGE_STORAGE_TYPE`: Set to "azure_blob" for Azure storage backend
- `STAC_STORAGE_AZURE_ACCOUNT_NAME`: Azure storage account name
- `STAC_STORAGE_AZURE_CONTAINER_NAME`: Azure blob container name
- `STAC_STORAGE_AZURE_AUTHENTICATION`: Authentication method ("managed_identity" or "sas_token")
- `STAC_STORAGE_AZURE_MANAGED_IDENTITY_CLIENT_ID`: Client ID for managed identity auth
- `STAC_STORAGE_AZURE_SAS_TOKEN`: SAS token for SAS token auth

## Local Development vs CI Environment Variables

The workflow uses different parquet URL formats for different environments:

- **Local Development**: `file://absolute/path/to/file.parquet`
- **Docker CI**: `file:///app/stac_collections/collection/file.parquet`
- **Azure**: `collections/collection/file.parquet` (relative to container)

This ensures that the same test data works across all environments while using the appropriate storage backend.