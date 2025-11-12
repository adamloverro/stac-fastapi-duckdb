#!/bin/bash

# Deploy Azure infrastructure for STAC FastAPI DuckDB integration testing
# This script creates all necessary Azure resources and generates SAS tokens

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BICEP_FILE="${SCRIPT_DIR}/main.bicep"
ENV_FILE="${SCRIPT_DIR}/.env.azure"

# Default values
RESOURCE_GROUP_NAME="${RESOURCE_GROUP_NAME:-stac-fastapi-duckdb-test}"
LOCATION="${LOCATION:-eastus2}"
ENVIRONMENT_NAME="${ENVIRONMENT_NAME:-test}"
STORAGE_ACCOUNT_NAME="${STORAGE_ACCOUNT_NAME:-}"
CONTAINER_NAME="${CONTAINER_NAME:-test-data}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if Azure CLI is installed and logged in
check_azure_cli() {
    print_status "Checking Azure CLI..."
    
    if ! command -v az &> /dev/null; then
        print_error "Azure CLI is not installed. Please install it first:"
        print_error "https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
        exit 1
    fi
    
    if ! az account show &> /dev/null; then
        print_error "Please log in to Azure CLI first: az login"
        exit 1
    fi
    
    local subscription=$(az account show --query name -o tsv)
    print_success "Logged in to Azure subscription: $subscription"
}

# Function to generate a unique storage account name if not provided
generate_storage_account_name() {
    if [[ -z "$STORAGE_ACCOUNT_NAME" ]]; then
        # Generate unique name using subscription ID hash
        local sub_id=$(az account show --query id -o tsv)
        local hash=$(echo "$sub_id" | sha256sum | cut -c1-8)
        STORAGE_ACCOUNT_NAME="stactest${hash}"
        print_status "Generated storage account name: $STORAGE_ACCOUNT_NAME"
    fi
}

# Function to create resource group
create_resource_group() {
    print_status "Creating resource group: $RESOURCE_GROUP_NAME"
    
    if az group show --name "$RESOURCE_GROUP_NAME" &> /dev/null; then
        print_warning "Resource group $RESOURCE_GROUP_NAME already exists"
    else
        az group create \
            --name "$RESOURCE_GROUP_NAME" \
            --location "$LOCATION" \
            --tags Purpose=STAC-FastAPI-DuckDB-Testing Environment="$ENVIRONMENT_NAME"
        print_success "Created resource group: $RESOURCE_GROUP_NAME"
    fi
}

# Function to deploy Bicep template
deploy_infrastructure() {
    print_status "Deploying Azure infrastructure..."
    
    local deployment_name="stac-fastapi-duckdb-$(date +%Y%m%d-%H%M%S)"
    
    az deployment group create \
        --resource-group "$RESOURCE_GROUP_NAME" \
        --name "$deployment_name" \
        --template-file "$BICEP_FILE" \
        --parameters \
            storageAccountName="$STORAGE_ACCOUNT_NAME" \
            containerName="$CONTAINER_NAME" \
            environmentName="$ENVIRONMENT_NAME" \
        --output json > "${SCRIPT_DIR}/deployment-output.json"
    
    print_success "Infrastructure deployment completed"
}

# Function to extract outputs from deployment
extract_deployment_outputs() {
    print_status "Extracting deployment outputs..."
    
    if [[ ! -f "${SCRIPT_DIR}/deployment-output.json" ]]; then
        print_error "Deployment output file not found"
        exit 1
    fi
    
    # Extract values using jq
    DEPLOYED_STORAGE_ACCOUNT=$(jq -r '.properties.outputs.storageAccountName.value' "${SCRIPT_DIR}/deployment-output.json")
    DEPLOYED_CONTAINER=$(jq -r '.properties.outputs.containerName.value' "${SCRIPT_DIR}/deployment-output.json")
    MANAGED_IDENTITY_CLIENT_ID=$(jq -r '.properties.outputs.managedIdentityClientId.value' "${SCRIPT_DIR}/deployment-output.json")
    TENANT_ID=$(jq -r '.properties.outputs.tenantId.value' "${SCRIPT_DIR}/deployment-output.json")
    SUBSCRIPTION_ID=$(jq -r '.properties.outputs.subscriptionId.value' "${SCRIPT_DIR}/deployment-output.json")
    
    print_success "Extracted deployment outputs"
}

# Function to generate SAS token
generate_sas_token() {
    print_status "Generating SAS token..."
    
    # Calculate expiry date (30 days from now)
    local expiry_date
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        expiry_date=$(date -u -v+30d +"%Y-%m-%dT%H:%M:%SZ")
    else
        # Linux
        expiry_date=$(date -u -d "+30 days" +"%Y-%m-%dT%H:%M:%SZ")
    fi
    
    # Generate SAS token with read and list permissions
    SAS_TOKEN=$(az storage container generate-sas \
        --account-name "$DEPLOYED_STORAGE_ACCOUNT" \
        --name "$DEPLOYED_CONTAINER" \
        --permissions rl \
        --expiry "$expiry_date" \
        --output tsv)
    
    print_success "Generated SAS token (expires: $expiry_date)"
}

# Function to assign Storage Blob Data Reader role to current user
assign_blob_data_reader_role() {
    print_status "Assigning Storage Blob Data Reader role to current user..."
    
    # Get current user's object ID
    local current_user_id
    current_user_id=$(az ad signed-in-user show --query id -o tsv)
    
    if [[ -z "$current_user_id" ]]; then
        print_error "Could not get current user ID"
        return 1
    fi
    
    print_status "Current user ID: $current_user_id"
    
    # Build the scope for the storage account
    local storage_account_scope="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP_NAME/providers/Microsoft.Storage/storageAccounts/$DEPLOYED_STORAGE_ACCOUNT"
    
    # Check if role assignment already exists
    local existing_assignment
    existing_assignment=$(az role assignment list \
        --assignee "$current_user_id" \
        --role "Storage Blob Data Reader" \
        --scope "$storage_account_scope" \
        --query '[].roleDefinitionName' \
        --output tsv 2>/dev/null || echo "")
    
    if [[ -n "$existing_assignment" ]]; then
        print_warning "Storage Blob Data Reader role already assigned to current user"
        return 0
    fi
    
    # Assign the role
    print_status "Assigning Storage Blob Data Reader role..."
    if az role assignment create \
        --assignee "$current_user_id" \
        --role "Storage Blob Data Reader" \
        --scope "$storage_account_scope" \
        --output none; then
        print_success "Successfully assigned Storage Blob Data Reader role to current user"
        print_status "This allows your Azure CLI credential to read blob data when using DefaultAzureCredential"
    else
        print_error "Failed to assign Storage Blob Data Reader role"
        print_warning "You may need to ask an administrator to assign this role, or use SAS token authentication instead"
        return 1
    fi
}

# Function to upload STAC collections data to Azure
create_test_data() {
    print_status "Uploading STAC collections data to Azure..."
    
    # Find the project root (go up from the script directory to find stac_collections)
    local project_root="${SCRIPT_DIR}/../../../.."
    local stac_collections_dir="${project_root}/stac_collections"
    
    # Check if stac_collections directory exists
    if [[ ! -d "$stac_collections_dir" ]]; then
        print_error "STAC collections directory not found at: $stac_collections_dir"
        print_status "Looking for stac_collections in current directory structure..."
        # Alternative search from current location
        if [[ -d "${PWD}/stac_collections" ]]; then
            stac_collections_dir="${PWD}/stac_collections"
            print_status "Found stac_collections at: $stac_collections_dir"
        else
            print_error "Cannot find stac_collections directory. Please ensure it exists in the project root."
            return 1
        fi
    fi
    
    print_status "Found STAC collections directory: $stac_collections_dir"
    
    # Upload all parquet files from stac_collections
    local uploaded_count=0
    
    # Generate collections registry with Azure URLs before uploading
    print_status "Generating collections registry with Azure URLs..."
    local geoparquet_script="${project_root}/geoparquet/create_collections_registry.py"
    local temp_registry="/tmp/collections_azure.parquet"
    
    if [[ -f "$geoparquet_script" ]]; then
        # Run the script with Azure-specific parameters
        python3 "$geoparquet_script" \
            --stac-dir "$stac_collections_dir" \
            --output "$temp_registry" \
            --azure-account "$DEPLOYED_STORAGE_ACCOUNT" \
            --azure-container "$DEPLOYED_CONTAINER" \
            2>&1
        
        if [[ -f "$temp_registry" ]]; then
            print_status "Uploading generated collections registry..."
            if az storage blob upload \
                --account-name "$DEPLOYED_STORAGE_ACCOUNT" \
                --container-name "$DEPLOYED_CONTAINER" \
                --name "collections.parquet" \
                --file "$temp_registry" \
                --overwrite \
                --output none; then
                print_success "✓ Uploaded: collections.parquet (Azure URLs)"
                ((uploaded_count++))
                rm -f "$temp_registry"
            else
                print_error "✗ Failed to upload: collections.parquet"
            fi
        else
            print_error "Failed to generate collections registry"
        fi
    else
        print_warning "Collections registry script not found at: $geoparquet_script"
        # Fallback: upload existing registry if available
        if [[ -f "${stac_collections_dir}/collections.parquet" ]]; then
            print_warning "Using existing collections.parquet (may have local paths)"
            if az storage blob upload \
                --account-name "$DEPLOYED_STORAGE_ACCOUNT" \
                --container-name "$DEPLOYED_CONTAINER" \
                --name "collections.parquet" \
                --file "${stac_collections_dir}/collections.parquet" \
                --overwrite \
                --output none; then
                print_success "✓ Uploaded: collections.parquet"
                ((uploaded_count++))
            else
                print_error "✗ Failed to upload: collections.parquet"
            fi
        fi
    fi
    
    # Find and upload all .parquet files from subdirectories
    while IFS= read -r -d '' parquet_file; do
        local filename=$(basename "$parquet_file")
        local collection_name=$(basename "$(dirname "$parquet_file")")
        
        # Skip the root-level collections.parquet (already uploaded above)
        if [[ "$filename" == "collections.parquet" && "$collection_name" == "stac_collections" ]]; then
            continue
        fi
        
        local blob_name="collections/${collection_name}/${filename}"
        
        print_status "Uploading $filename from collection $collection_name..."
        
        if az storage blob upload \
            --account-name "$DEPLOYED_STORAGE_ACCOUNT" \
            --container-name "$DEPLOYED_CONTAINER" \
            --name "$blob_name" \
            --file "$parquet_file" \
            --overwrite \
            --output none; then
            print_success "✓ Uploaded: $blob_name"
            ((uploaded_count++))
        else
            print_error "✗ Failed to upload: $blob_name"
        fi
    done < <(find "$stac_collections_dir" -name "*.parquet" -type f -print0)
    
    # Also upload collection.json files for reference
    while IFS= read -r -d '' collection_file; do
        local filename=$(basename "$collection_file")
        local collection_name=$(basename "$(dirname "$collection_file")")
        local blob_name="collections/${collection_name}/${filename}"
        
        print_status "Uploading $filename from collection $collection_name..."
        
        if az storage blob upload \
            --account-name "$DEPLOYED_STORAGE_ACCOUNT" \
            --container-name "$DEPLOYED_CONTAINER" \
            --name "$blob_name" \
            --file "$collection_file" \
            --overwrite \
            --output none; then
            print_success "✓ Uploaded: $blob_name"
            ((uploaded_count++))
        else
            print_error "✗ Failed to upload: $blob_name"
        fi
    done < <(find "$stac_collections_dir" -name "collection.json" -type f -print0)
    
    if [[ $uploaded_count -gt 0 ]]; then
        print_success "Successfully uploaded $uploaded_count files to Azure Blob Storage"
        
        # List the uploaded files for verification
        print_status "Verifying uploaded files..."
        az storage blob list \
            --account-name "$DEPLOYED_STORAGE_ACCOUNT" \
            --container-name "$DEPLOYED_CONTAINER" \
            --prefix "collections/" \
            --query "[].{Name:name, Size:properties.contentLength}" \
            --output table
    else
        print_warning "No files were uploaded. Check if parquet files exist in $stac_collections_dir"
    fi
}

# Function to save environment variables
save_environment_variables() {
    print_status "Saving environment variables to $ENV_FILE"
    
    cat > "$ENV_FILE" << EOF
# Azure Integration Test Environment Variables
# Generated on $(date)
# 
# Load these variables before running integration tests:
# source ${ENV_FILE}

export AZURE_STORAGE_ACCOUNT="$DEPLOYED_STORAGE_ACCOUNT"
export AZURE_TEST_CONTAINER="$DEPLOYED_CONTAINER"
export AZURE_SAS_TOKEN="$SAS_TOKEN"
export AZURE_CLIENT_ID="$MANAGED_IDENTITY_CLIENT_ID"
export AZURE_TENANT_ID="$TENANT_ID"
export AZURE_SUBSCRIPTION_ID="$SUBSCRIPTION_ID"
export AZURE_RESOURCE_GROUP="$RESOURCE_GROUP_NAME"

# Additional variables for reference
export AZURE_RESOURCE_GROUP_NAME="$RESOURCE_GROUP_NAME"
export AZURE_LOCATION="$LOCATION"
export AZURE_ENVIRONMENT_NAME="$ENVIRONMENT_NAME"
EOF
    
    chmod 600 "$ENV_FILE"
    print_success "Environment variables saved to $ENV_FILE"
}

# Function to display summary
display_summary() {
    echo
    echo "======================================"
    echo "Azure Infrastructure Deployment Complete"
    echo "======================================"
    echo
    echo "Resources created:"
    echo "  Resource Group: $RESOURCE_GROUP_NAME"
    echo "  Storage Account: $DEPLOYED_STORAGE_ACCOUNT"
    echo "  Container: $DEPLOYED_CONTAINER"
    echo "  Managed Identity: ${DEPLOYED_STORAGE_ACCOUNT}-identity"
    echo
    echo "Permissions configured:"
    echo "  ✓ Current user has Storage Blob Data Reader role"
    echo "  ✓ SAS token with read/list permissions generated"
    echo "  ✓ Managed identity configured for Azure deployments"
    echo
    echo "To run integration tests:"
    echo "  1. Load environment variables:"
    echo "     source $ENV_FILE"
    echo
    echo "  2. Run integration tests:"
    echo "     make test-azure-integration"
    echo
    echo "Authentication methods available:"
    echo "  • SAS Token: Works everywhere (expires in 30 days)"
    echo "  • Azure CLI (DefaultAzureCredential): Works locally with your permissions"
    echo "  • Managed Identity: Works in Azure deployments"
    echo
    echo "To clean up resources:"
    echo "  make azure-teardown"
    echo
    print_warning "SAS token expires in 30 days. Re-run deployment to regenerate."
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Deploy Azure infrastructure for STAC FastAPI DuckDB integration testing"
    echo
    echo "Options:"
    echo "  -h, --help                    Show this help message"
    echo "  -g, --resource-group NAME     Resource group name (default: stac-fastapi-duckdb-test)"
    echo "  -l, --location LOCATION       Azure location (default: eastus2)"
    echo "  -s, --storage-account NAME    Storage account name (auto-generated if not provided)"
    echo "  -c, --container NAME          Container name (default: test-data)"
    echo "  -e, --environment NAME        Environment name (default: test)"
    echo
    echo "Environment variables:"
    echo "  RESOURCE_GROUP_NAME           Override default resource group name"
    echo "  LOCATION                      Override default location"
    echo "  STORAGE_ACCOUNT_NAME          Override storage account name"
    echo "  CONTAINER_NAME                Override container name"
    echo "  ENVIRONMENT_NAME              Override environment name"
    echo
    echo "Examples:"
    echo "  $0                                          # Use all defaults"
    echo "  $0 -g my-test-rg -l westus2                # Custom resource group and location"
    echo "  $0 -s mystorageaccount123                  # Custom storage account name"
}

# Parse command line arguments
parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -g|--resource-group)
                RESOURCE_GROUP_NAME="$2"
                shift 2
                ;;
            -l|--location)
                LOCATION="$2"
                shift 2
                ;;
            -s|--storage-account)
                STORAGE_ACCOUNT_NAME="$2"
                shift 2
                ;;
            -c|--container)
                CONTAINER_NAME="$2"
                shift 2
                ;;
            -e|--environment)
                ENVIRONMENT_NAME="$2"
                shift 2
                ;;
            *)
                print_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
}

# Main execution
main() {
    echo "STAC FastAPI DuckDB - Azure Infrastructure Deployment"
    echo "===================================================="
    echo
    
    parse_arguments "$@"
    
    # Check prerequisites
    check_azure_cli
    
    # Check for required tools
    if ! command -v jq &> /dev/null; then
        print_error "jq is required but not installed. Please install jq first."
        exit 1
    fi
    
    # Generate storage account name if not provided
    generate_storage_account_name
    
    # Deploy infrastructure
    create_resource_group
    deploy_infrastructure
    extract_deployment_outputs
    generate_sas_token
    assign_blob_data_reader_role
    create_test_data
    save_environment_variables
    display_summary
    
    print_success "Deployment completed successfully!"
}

# Run main function with all arguments
main "$@"