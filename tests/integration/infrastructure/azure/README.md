# Azure Integration Testing

This directory contains infrastructure and integration tests for testing the STAC FastAPI DuckDB Azure Blob Storage backend with real Azure resources.

## Overview

The Azure integration testing setup provides:

- **Real Azure Blob Storage testing**: Tests actual connectivity and operations with Azure
- **Multiple authentication methods**: SAS token and managed identity authentication
- **Infrastructure as Code**: Bicep templates for consistent, reproducible deployments
- **Automated deployment/teardown**: Scripts to create and destroy test environments
- **DuckDB integration**: Tests that verify DuckDB can read from Azure URLs

## Quick Start

### Prerequisites

1. **Azure CLI**: [Install Azure CLI](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli)
2. **jq**: JSON processor for parsing Azure CLI output
   ```bash
   # macOS
   brew install jq
   
   # Ubuntu/Debian
   sudo apt-get install jq
   ```
3. **Azure Subscription**: Active Azure subscription with contributor access
4. **Python Dependencies**: Azure storage packages (install with `pip install -e .[azure]`)

### Basic Usage

1. **Login to Azure**:
   ```bash
   az login
   ```

2. **Deploy test infrastructure**:
   ```bash
   make azure-deploy
   ```

3. **Load environment variables**:
   ```bash
   source tests/integration/infrastructure/azure/.env.azure
   ```

4. **Run integration tests**:
   ```bash
   make test-azure-integration
   ```

5. **Clean up resources**:
   ```bash
   make azure-teardown
   ```

## Infrastructure Components

### Azure Resources Created

The deployment creates the following Azure resources:

- **Storage Account**: Blob storage for test data
- **Blob Container**: Container for storing test parquet files
- **Managed Identity**: User-assigned identity for managed identity authentication
- **Role Assignments**: Permissions for the managed identity to access storage

### Resource Naming

- **Resource Group**: `stac-fastapi-duckdb-test` (customizable)
- **Storage Account**: `stactest<hash>` (auto-generated unique name)
- **Container**: `test-data` (customizable)
- **Managed Identity**: `<storage-account>-identity`

## Deployment Script Options

### Basic Deployment

```bash
# Use all defaults
make azure-deploy
```

### Custom Configuration

You can still use the deployment script directly for custom configuration:

```bash
# Custom resource group and location
./tests/integration/infrastructure/azure/deploy.sh -g my-test-rg -l westus2

# Custom storage account name
./tests/integration/infrastructure/azure/deploy.sh -s mystorageaccount123

# All options
./tests/integration/infrastructure/azure/deploy.sh \
  --resource-group my-rg \
  --location eastus \
  --storage-account myuniquestorage123 \
  --container my-test-container \
  --environment dev
```

### Environment Variables

You can also set options via environment variables:

```bash
export RESOURCE_GROUP_NAME="my-test-rg"
export LOCATION="westus2"
export STORAGE_ACCOUNT_NAME="mystorageaccount123"
export CONTAINER_NAME="my-container"
export ENVIRONMENT_NAME="dev"

make azure-deploy
```

## Integration Tests

### Test Categories

The integration tests are organized into several categories:

1. **Connection Tests**: Verify that both SAS token and managed identity authentication work
2. **URL Generation Tests**: Ensure generated URLs are correctly formatted and accessible
3. **Error Handling Tests**: Test behavior with invalid credentials/resources
4. **DuckDB Integration Tests**: Verify DuckDB can read from generated Azure URLs

### Running Tests

```bash
# Run all integration tests (using make command)
make test-azure-integration

# Run with coverage
make test-azure-integration-with-coverage

# Alternative: Run directly with pytest
source tests/integration/infrastructure/azure/.env.azure
pytest tests/integration/test_azure_integration.py -v -m integration

# Run specific test
pytest tests/integration/test_azure_integration.py::TestAzureIntegration::test_azure_sas_token_connection -v

# Dry run (check test discovery without execution)
pytest tests/integration/ --collect-only
```

### Test Environment Variables

The integration tests require these environment variables (automatically set by deployment script):

```bash
AZURE_STORAGE_ACCOUNT      # Storage account name
AZURE_TEST_CONTAINER       # Container name
AZURE_SAS_TOKEN            # SAS token for authentication
AZURE_CLIENT_ID            # Managed identity client ID
AZURE_TENANT_ID            # Azure tenant ID
AZURE_SUBSCRIPTION_ID      # Azure subscription ID
```

## Teardown Script Options

### Basic Teardown

```bash
# Remove all resources (with confirmation)
make azure-teardown
```

### Advanced Options

```bash
# Force deletion without confirmation (DANGEROUS)
make azure-teardown-force

# Dry run (see what would be deleted)
make azure-dry-run

# Check current status
make azure-status

# Direct script usage for custom options
./tests/integration/infrastructure/azure/teardown.sh -g my-custom-rg
```

## Troubleshooting

### Common Issues

1. **Azure CLI not logged in**:
   ```bash
   az login
   ```

2. **Insufficient permissions**:
   - Ensure your Azure account has Contributor access to the subscription
   - Check if your organization has policy restrictions

3. **Storage account name conflicts**:
   - Storage account names must be globally unique
   - Use a custom name: `./deploy.sh -s myuniquename123`

4. **SAS token expired**:
   - SAS tokens expire after 30 days
   - Re-run deployment to generate new token

5. **Managed identity authentication fails**:
   - Managed identity only works in Azure environments (VMs, Container Instances, etc.)
   - Local development machines will skip these tests

### Debug Information

The deployment script creates several files for debugging:

- `tests/integration/infrastructure/azure/.env.azure`: Environment variables
- `tests/integration/infrastructure/azure/deployment-output.json`: Raw deployment output

### Manual Resource Inspection

```bash
# Load environment variables
source tests/integration/infrastructure/azure/.env.azure

# Check infrastructure status
make azure-status

# List all resources in the group
az resource list --resource-group "$AZURE_RESOURCE_GROUP_NAME" --output table

# Check storage account details
az storage account show --name "$AZURE_STORAGE_ACCOUNT" --output table

# List blobs in container
az storage blob list --account-name "$AZURE_STORAGE_ACCOUNT" --container-name "$AZURE_TEST_CONTAINER" --output table

# Test SAS token
curl -I "https://$AZURE_STORAGE_ACCOUNT.blob.core.windows.net/$AZURE_TEST_CONTAINER/collections/io-lulc-9-class/io-lulc-9-class.parquet?$AZURE_SAS_TOKEN"
```

## Cost Management

### Resource Costs

The test infrastructure uses minimal Azure resources:

- **Storage Account**: Standard LRS (lowest cost tier)
- **Blob Storage**: Hot tier for test data
- **Managed Identity**: No additional cost

Estimated cost: **~$1-5 USD per month** depending on usage.

### Cost Optimization

- Delete resources immediately after testing: `make azure-teardown`
- Use Azure Free Tier if available
- Set up Azure budgets and alerts for cost monitoring

## Security Considerations

### Permissions

The deployment follows security best practices:

- **Minimal permissions**: Managed identity only has Blob Data Reader/Contributor access
- **Private containers**: No public blob access enabled
- **Time-limited SAS tokens**: 30-day expiration
- **HTTPS only**: All storage access requires HTTPS

### Secrets Management

- **Environment file protection**: `.env.azure` has restricted permissions (600)
- **No secrets in code**: All credentials are generated and stored locally
- **SAS token rotation**: Re-deploy to generate new tokens

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Azure Integration Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  azure-integration:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' || (github.event_name == 'pull_request' && contains(github.event.pull_request.labels.*.name, 'test-azure'))
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Setup Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install -e .[dev,azure]
    
    - name: Azure Login
      uses: azure/login@v1
      with:
        creds: ${{ secrets.AZURE_CREDENTIALS }}
    
    - name: Deploy test infrastructure
      run: |
        make azure-deploy
    
    - name: Run integration tests
      run: |
        make test-azure-integration
    
    - name: Cleanup resources
      if: always()
      run: |
        make azure-teardown-force
```

### Required Secrets

For CI/CD, create these GitHub secrets:

- `AZURE_CREDENTIALS`: Service principal credentials for Azure login

## Development Workflow

### Adding New Tests

1. Add test methods to `TestAzureIntegration` class
2. Use `@pytest.mark.integration` decorator
3. Use fixtures for Azure configuration
4. Handle environment-specific variations (managed identity)

### Extending Infrastructure

1. Modify `tests/integration/infrastructure/azure/main.bicep` for new resources
2. Update `tests/integration/infrastructure/azure/deploy.sh` to handle new outputs
3. Add corresponding environment variables
4. Update teardown script if needed

## File Structure

```
tests/integration/
├── test_azure_integration.py        # Integration tests
└── infrastructure/azure/
    ├── README.md                     # This documentation
    ├── main.bicep                    # Infrastructure template
    ├── deploy.sh                     # Deployment script
    ├── teardown.sh                   # Cleanup script
    ├── .env.azure.example            # Example environment variables
    ├── .env.azure                    # Generated environment variables (gitignored)
    ├── deployment-output.json        # Generated deployment output (gitignored)
    └── .gitignore                    # Git ignore file
```

## Make Commands Reference

| Command | Description |
|---------|-------------|
| `make azure-deploy` | Deploy Azure infrastructure |
| `make azure-teardown` | Teardown infrastructure with confirmation |
| `make azure-teardown-force` | Force teardown without confirmation |
| `make azure-dry-run` | Show what would be deleted (dry run) |
| `make azure-status` | Check current infrastructure status |
| `make test-azure-integration` | Run integration tests |
| `make test-azure-integration-with-coverage` | Run tests with coverage |

## Additional Resources

- [Azure CLI Documentation](https://docs.microsoft.com/en-us/cli/azure/)
- [Azure Bicep Documentation](https://docs.microsoft.com/en-us/azure/azure-resource-manager/bicep/)
- [Azure Storage Documentation](https://docs.microsoft.com/en-us/azure/storage/)
- [Azure Managed Identity Documentation](https://docs.microsoft.com/en-us/azure/active-directory/managed-identities-azure-resources/)
- [DuckDB httpfs Extension](https://duckdb.org/docs/extensions/httpfs)