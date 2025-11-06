SHELL := /bin/bash

.DEFAULT_GOAL := help

PROJECT_ROOT := $(abspath .)
STAC_DIR := $(PROJECT_ROOT)/stac_collections
DEMO_PARQUET := $(STAC_DIR)/io-lulc-9-class/io-lulc-9-class.parquet
PARQUET_URL := file:///app/stac_collections/io-lulc-9-class/io-lulc-9-class.parquet


help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS=":.*##"} {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

build: ## Build docker image
	docker compose build

up: ## Run docker compose in foreground with demo env
	STAC_FILE_PATH="$(STAC_DIR)" PARQUET_URLS_JSON='{"io-lulc-9-class":"$(PARQUET_URL)"}' docker compose up

up-d: ## Run docker compose detached with demo env
	STAC_FILE_PATH="$(STAC_DIR)" PARQUET_URLS_JSON='{"io-lulc-9-class":"$(PARQUET_URL)"}' docker compose up -d

down: ## Stop containers
	docker compose down

logs: ## Tail logs
	docker compose logs -f

DOCKER_ENV = STAC_FILE_PATH="$(STAC_DIR)" \
	PARQUET_URLS_JSON='{"io-lulc-9-class":"$(PARQUET_URL)"}'

LOCAL_ENV = STAC_FILE_PATH="$(STAC_DIR)" \
	PARQUET_URLS_JSON='{"io-lulc-9-class":"file://$(DEMO_PARQUET)"}'

up-local: ## Run the FastAPI app locally without Docker
	@echo "Starting STAC FastAPI DuckDB server locally..."
	@echo "Server will be available at: http://localhost:8000"
	@echo "Press Ctrl+C to stop"
	$(LOCAL_ENV) python -m stac_fastapi.duckdb.app

test-local: ## Run pytest test suite locally
	@echo "Running local tests..."
	$(LOCAL_ENV) pytest tests/ -v

test: ## Run tests in docker
	$(DOCKER_ENV) docker compose exec app-duckdb pytest tests/ -v

test-build: ## Build and run tests in docker
	$(DOCKER_ENV) docker compose build
	$(DOCKER_ENV) docker compose up -d
	@echo "Waiting for containers to be ready..."
	@sleep 5
	$(DOCKER_ENV) docker compose exec app-duckdb pytest tests/ -v
	$(DOCKER_ENV) docker compose down

restart: down up-d ## Restart detached

demo-url: ## Print demo PARQUET_URLS_JSON
	@echo '{"io-lulc-9-class":"$(PARQUET_URL)"}'

# --- Demo helpers ---
demo: ## Build image and run demo (detached)
	$(MAKE) build
	$(MAKE) up-d
	@echo "\nDemo running at: http://localhost:8085"
	@echo "Try:"
	@echo "  - http://localhost:8085/collections"
	@echo "  - http://localhost:8085/collections/io-lulc-9-class"
	@echo "  - http://localhost:8085/collections/io-lulc-9-class/items?limit=1"

demo-down: ## Stop the demo containers
	$(MAKE) down

demo-logs: ## Tail demo logs
	$(MAKE) logs

# --- Azure Integration Testing ---
AZURE_INFRA_DIR := $(PROJECT_ROOT)/tests/integration/infrastructure/azure

azure-deploy: ## Deploy Azure infrastructure for integration testing
	@echo "Deploying Azure infrastructure for integration testing..."
	@if [ ! -f "$(AZURE_INFRA_DIR)/deploy.sh" ]; then \
		echo "Error: Azure deployment script not found at $(AZURE_INFRA_DIR)/deploy.sh"; \
		exit 1; \
	fi
	@cd "$(AZURE_INFRA_DIR)" && ./deploy.sh
	@echo ""
	@echo "Azure infrastructure deployed successfully!"
	@echo "Next steps:"
	@echo "  1. Load environment variables:"
	@echo "     source $(AZURE_INFRA_DIR)/.env.azure"
	@echo "  2. Run integration tests:"
	@echo "     make test-azure-integration"

azure-teardown: ## Teardown Azure infrastructure
	@echo "Tearing down Azure infrastructure..."
	@if [ ! -f "$(AZURE_INFRA_DIR)/teardown.sh" ]; then \
		echo "Error: Azure teardown script not found at $(AZURE_INFRA_DIR)/teardown.sh"; \
		exit 1; \
	fi
	@cd "$(AZURE_INFRA_DIR)" && ./teardown.sh

azure-teardown-force: ## Force teardown Azure infrastructure without confirmation
	@echo "Force tearing down Azure infrastructure (no confirmation)..."
	@if [ ! -f "$(AZURE_INFRA_DIR)/teardown.sh" ]; then \
		echo "Error: Azure teardown script not found at $(AZURE_INFRA_DIR)/teardown.sh"; \
		exit 1; \
	fi
	@cd "$(AZURE_INFRA_DIR)" && ./teardown.sh --force

test-azure-integration: ## Run Azure integration tests (requires deployed infrastructure)
	@echo "Running Azure integration tests..."
	@if [ ! -f "$(AZURE_INFRA_DIR)/.env.azure" ]; then \
		echo "Error: Azure environment file not found."; \
		echo "Please deploy Azure infrastructure first: make azure-deploy"; \
		exit 1; \
	fi
	@echo "Loading Azure environment variables..."
	@source "$(AZURE_INFRA_DIR)/.env.azure" && \
		pytest tests/integration/test_azure_integration.py -v -m integration

test-azure-integration-with-coverage: ## Run Azure integration tests with coverage
	@echo "Running Azure integration tests with coverage..."
	@if [ ! -f "$(AZURE_INFRA_DIR)/.env.azure" ]; then \
		echo "Error: Azure environment file not found."; \
		echo "Please deploy Azure infrastructure first: make azure-deploy"; \
		exit 1; \
	fi
	@echo "Loading Azure environment variables..."
	@source "$(AZURE_INFRA_DIR)/.env.azure" && \
		pytest tests/integration/test_azure_integration.py -v -m integration \
			--cov=stac_fastapi.duckdb.storage.azure \
			--cov-report=html \
			--cov-report=term

azure-status: ## Check status of Azure infrastructure
	@echo "Checking Azure infrastructure status..."
	@if [ -f "$(AZURE_INFRA_DIR)/.env.azure" ]; then \
		echo "Azure environment file found: $(AZURE_INFRA_DIR)/.env.azure"; \
		source "$(AZURE_INFRA_DIR)/.env.azure" && \
		echo "Resource Group: $$AZURE_RESOURCE_GROUP_NAME" && \
		echo "Storage Account: $$AZURE_STORAGE_ACCOUNT" && \
		echo "Container: $$AZURE_TEST_CONTAINER" && \
		if command -v az >/dev/null 2>&1; then \
			echo "Checking if resources exist..." && \
			if az group show --name "$$AZURE_RESOURCE_GROUP_NAME" >/dev/null 2>&1; then \
				echo "✓ Resource group exists"; \
				az resource list --resource-group "$$AZURE_RESOURCE_GROUP_NAME" --query '[].{Name:name, Type:type}' --output table; \
			else \
				echo "✗ Resource group does not exist"; \
			fi; \
		else \
			echo "(Azure CLI not available for resource verification)"; \
		fi; \
	else \
		echo "No Azure environment file found."; \
		echo "Deploy Azure infrastructure with: make azure-deploy"; \
	fi

azure-dry-run: ## Show what Azure resources would be deleted (dry run)
	@echo "Azure teardown dry run..."
	@if [ ! -f "$(AZURE_INFRA_DIR)/teardown.sh" ]; then \
		echo "Error: Azure teardown script not found at $(AZURE_INFRA_DIR)/teardown.sh"; \
		exit 1; \
	fi
	@cd "$(AZURE_INFRA_DIR)" && ./teardown.sh --dry-run
