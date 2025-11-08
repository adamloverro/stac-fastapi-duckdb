#!/bin/bash

# Teardown Azure infrastructure for STAC FastAPI DuckDB integration testing
# This script completely removes all Azure resources created by deploy.sh

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env.azure"

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

# Function to load environment variables if available
load_environment() {
    if [[ -f "$ENV_FILE" ]]; then
        print_status "Loading environment variables from $ENV_FILE"
        source "$ENV_FILE"
        
        if [[ -n "${AZURE_RESOURCE_GROUP_NAME:-}" ]]; then
            RESOURCE_GROUP_NAME="$AZURE_RESOURCE_GROUP_NAME"
        fi
    fi
}

# Function to prompt for confirmation
confirm_deletion() {
    echo
    print_warning "======================================"
    print_warning "DESTRUCTIVE OPERATION WARNING"
    print_warning "======================================"
    echo
    print_warning "This will permanently delete the following resources:"
    
    if [[ -n "${RESOURCE_GROUP_NAME:-}" ]]; then
        echo "  • Resource Group: $RESOURCE_GROUP_NAME"
        echo "  • All resources within the resource group:"
        
        # List resources if resource group exists
        if az group show --name "$RESOURCE_GROUP_NAME" &> /dev/null; then
            az resource list --resource-group "$RESOURCE_GROUP_NAME" --query '[].{Name:name, Type:type}' --output table 2>/dev/null || true
        fi
    else
        print_error "No resource group specified. Cannot proceed."
        exit 1
    fi
    
    echo
    print_warning "This action cannot be undone!"
    echo
    
    read -p "Are you sure you want to delete these resources? (type 'yes' to confirm): " confirmation
    
    if [[ "$confirmation" != "yes" ]]; then
        print_status "Deletion cancelled."
        exit 0
    fi
}

# Function to delete resource group and all resources
delete_resources() {
    print_status "Deleting resource group: $RESOURCE_GROUP_NAME"
    
    if ! az group show --name "$RESOURCE_GROUP_NAME" &> /dev/null; then
        print_warning "Resource group $RESOURCE_GROUP_NAME does not exist or has already been deleted"
        return 0
    fi
    
    # Delete the resource group (this deletes all contained resources)
    print_status "Starting resource group deletion..."
    az group delete \
        --name "$RESOURCE_GROUP_NAME" \
        --yes \
        --no-wait
    
    print_success "Resource group deletion initiated"
    print_status "Waiting for deletion to complete (this may take several minutes)..."
    
    # Wait for deletion to complete
    local max_attempts=60  # 5 minutes with 5-second intervals
    local attempt=1
    
    while [[ $attempt -le $max_attempts ]]; do
        if ! az group show --name "$RESOURCE_GROUP_NAME" &> /dev/null; then
            print_success "Resource group deletion completed"
            return 0
        fi
        
        echo -n "."
        sleep 5
        ((attempt++))
    done
    
    echo
    print_warning "Resource group deletion is taking longer than expected"
    print_status "You can check the status in the Azure portal or with:"
    print_status "az group show --name $RESOURCE_GROUP_NAME"
}

# Function to clean up local files
cleanup_local_files() {
    print_status "Cleaning up local deployment files..."
    
    local files_to_remove=(
        "$ENV_FILE"
        "${SCRIPT_DIR}/deployment-output.json"
    )
    
    for file in "${files_to_remove[@]}"; do
        if [[ -f "$file" ]]; then
            rm "$file"
            print_status "Removed: $file"
        fi
    done
    
    print_success "Local cleanup completed"
}

# Function to display summary
display_summary() {
    echo
    echo "======================================"
    echo "Azure Infrastructure Teardown Complete"
    echo "======================================"
    echo
    
    if [[ -n "${RESOURCE_GROUP_NAME:-}" ]]; then
        echo "Deleted resource group: $RESOURCE_GROUP_NAME"
        echo "All contained resources have been removed."
    fi
    
    echo
    echo "Cleaned up local files:"
    echo "  • Environment variables file"
    echo "  • Deployment output file"
    echo
    print_success "Teardown completed successfully!"
    echo
    print_status "To deploy again, run: ./infrastructure/azure/deploy.sh"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Teardown Azure infrastructure for STAC FastAPI DuckDB integration testing"
    echo
    echo "Options:"
    echo "  -h, --help                    Show this help message"
    echo "  -g, --resource-group NAME     Resource group name to delete"
    echo "  -f, --force                   Skip confirmation prompt (DANGEROUS)"
    echo "  --dry-run                     Show what would be deleted without actually deleting"
    echo
    echo "The script will attempt to load the resource group name from:"
    echo "  1. Command line argument (-g/--resource-group)"
    echo "  2. Environment file (.env.azure)"
    echo "  3. Default value (stac-fastapi-duckdb-test)"
    echo
    echo "Examples:"
    echo "  $0                           # Use resource group from .env.azure or default"
    echo "  $0 -g my-test-rg            # Delete specific resource group"
    echo "  $0 --dry-run                # Show what would be deleted"
    echo "  $0 -f                       # Force deletion without confirmation"
}

# Function to perform dry run
dry_run() {
    print_status "DRY RUN MODE - No resources will be deleted"
    echo
    
    if [[ -n "${RESOURCE_GROUP_NAME:-}" ]]; then
        if az group show --name "$RESOURCE_GROUP_NAME" &> /dev/null; then
            print_status "Would delete resource group: $RESOURCE_GROUP_NAME"
            print_status "Resources that would be deleted:"
            az resource list --resource-group "$RESOURCE_GROUP_NAME" --query '[].{Name:name, Type:type}' --output table
        else
            print_warning "Resource group $RESOURCE_GROUP_NAME does not exist"
        fi
    else
        print_error "No resource group specified for dry run"
    fi
    
    echo
    print_status "Local files that would be cleaned up:"
    
    local files_to_remove=(
        "$ENV_FILE"
        "${SCRIPT_DIR}/deployment-output.json"
    )
    
    for file in "${files_to_remove[@]}"; do
        if [[ -f "$file" ]]; then
            echo "  • $file"
        fi
    done
    
    echo
    print_status "DRY RUN COMPLETE - No changes made"
}

# Parse command line arguments
parse_arguments() {
    local force_mode=false
    local dry_run_mode=false
    
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
            -f|--force)
                force_mode=true
                shift
                ;;
            --dry-run)
                dry_run_mode=true
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    # Set global flags
    FORCE_MODE=$force_mode
    DRY_RUN_MODE=$dry_run_mode
}

# Main execution
main() {
    echo "STAC FastAPI DuckDB - Azure Infrastructure Teardown"
    echo "=================================================="
    echo
    
    # Parse arguments
    parse_arguments "$@"
    
    # Check prerequisites
    check_azure_cli
    
    # Load environment variables
    load_environment
    
    # Set default resource group if not specified
    RESOURCE_GROUP_NAME="${RESOURCE_GROUP_NAME:-stac-fastapi-duckdb-test}"
    
    # Handle dry run mode
    if [[ "$DRY_RUN_MODE" == true ]]; then
        dry_run
        exit 0
    fi
    
    # Confirm deletion unless in force mode
    if [[ "$FORCE_MODE" != true ]]; then
        confirm_deletion
    fi
    
    # Perform teardown
    delete_resources
    cleanup_local_files
    display_summary
}

# Initialize variables
RESOURCE_GROUP_NAME=""
FORCE_MODE=false
DRY_RUN_MODE=false

# Run main function with all arguments
main "$@"