# stac-fastapi-duckdb

<!-- markdownlint-disable MD033 MD041 -->

<p align="left">
  <img src="https://github.com/radiantearth/stac-site/raw/master/images/logo/stac-030-long.png" width=600>
</p>

### DuckDB backend for the stac-fastapi project built on top of the [sfeos](https://github.com/stac-utils/stac-fastapi-elasticsearch-opensearch) core api library.

## Technologies

This project is built on the following technologies: STAC, stac-fastapi, SFEOS core, FastAPI, DuckDB, Python

<p align="left">
  <a href="https://stacspec.org/"><img src="https://raw.githubusercontent.com/stac-utils/stac-fastapi-elasticsearch-opensearch/refs/heads/main/assets/STAC-01.png" alt="STAC" height="100" hspace="10"></a>
  <a href="https://www.python.org/"><img src="https://raw.githubusercontent.com/stac-utils/stac-fastapi-elasticsearch-opensearch/refs/heads/main/assets/python.png" alt="Python" height="80" hspace="10"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://raw.githubusercontent.com/stac-utils/stac-fastapi-elasticsearch-opensearch/refs/heads/main/assets/fastapi.svg" alt="FastAPI" height="80" hspace="10"></a>
  <a href="https://duckdb.org/"><img src="https://raw.githubusercontent.com/Healy-Hyperspatial/stac-fastapi-duckdb/refs/heads/main/assets/duckdb-icon-logo-png.png" alt="DuckDB" height="80" hspace="10"></a>
  <a href="https://github.com/stac-utils/stac-fastapi-elasticsearch-opensearch"><img src="https://raw.githubusercontent.com/Healy-Hyperspatial/stac-fastapi-mongo/refs/heads/main/assets/sfeos-bw.png" alt="stac-fastapi-core" height="83" hspace="10"></a>
</p>

## Table of Contents

- [Quick Start with Docker](#quick-start-with-docker)
- [Local Development](#local-development)
- [Usage](#usage)
  - [Supported Query Parameters](#supported-query-parameters)
  - [Example Queries](#example-queries)
- [Configuration](#configuration)
  - [Environment Variables](#environment-variables)
- [Development](#development)
  - [Running Tests](#running-tests)
  - [Pre-commit](#pre-commit)

## Quick Start with Docker

The easiest way to get started is using Docker and the provided Makefile:

1. **Clone the repository** (if you haven't already):
   ```bash
   git clone https://github.com/Healy-Hyperspatial/stac-fastapi-duckdb.git
   cd stac-fastapi-duckdb
   ```

2. **Build and start the Docker container**:
   ```bash
   make up
   ```
   This will:
   - Build the Docker image
   - Start the STAC API server on http://localhost:8085
   - Mount the `stac_collections` directory into the container

3. **Access the API**:
   - Browse collections: http://localhost:8085/collections
   - View collection items: http://localhost:8085/collections/io-lulc-9-class/items
   - Get a specific item: http://localhost:8085/collections/io-lulc-9-class/items/{item_id}

4. **Other useful commands**:
   ```bash
   # Run in detached mode (background)
   make up-d
   
   # View logs
   make logs
   
   # Stop the container
   make down
   ```

## Local Development

For local development without Docker, you can run the FastAPI server and tests directly on your machine:

### Prerequisites

1. **Install Python dependencies**:
   ```bash
   pip install -e .[dev,server]
   ```

2. **Install pre-commit hooks** (optional but recommended):
   ```bash
   pre-commit install
   ```

### Running the Server Locally

```bash
# Run the FastAPI server locally on http://localhost:8000
make up-local
```

This will start the server using your local Python environment with the demo data.

### Running Tests Locally

```bash
# Run the full test suite locally
make test-local
```

This runs pytest against your local environment, which is faster than Docker-based testing.

### Manual Commands

If you prefer to run commands manually, you can use:

```bash
# Start server manually
STAC_FILE_PATH="./stac_collections" \
PARQUET_URLS_JSON='{"io-lulc-9-class":"file://./stac_collections/io-lulc-9-class/io-lulc-9-class.parquet"}' \
python -m stac_fastapi.duckdb.app

# Run tests manually  
STAC_FILE_PATH="./stac_collections" \
PARQUET_URLS_JSON='{"io-lulc-9-class":"file://./stac_collections/io-lulc-9-class/io-lulc-9-class.parquet"}' \
pytest tests/ -v
```

## API Endpoints

The following STAC API endpoints are implemented:
- `GET /collections` - List all collections
- `GET /collections/{collection_id}` - Get a specific collection
- `GET /collections/{collection_id}/items` - Get items in a collection with filtering support (bbox, datetime)
- `GET /collections/{collection_id}/items/{item_id}` - Get a specific item
- `POST /search` - Search across collections with advanced filtering (bbox, datetime, etc.)

Both the GET items endpoint and POST search endpoint support bbox filtering. The GET endpoint accepts bbox as a comma-separated string query parameter, while the POST endpoint accepts bbox as either a comma-separated string or an array of numbers in the request body.

### Supported Query Parameters

#### Spatial Filtering
- `bbox` - Filter items by bounding box in format `west,south,east,north`
  - Example: `bbox=-66,-16,-60,-8`
  - Uses DuckDB's spatial extension with ST_Intersects for efficient filtering

#### Temporal Filtering
- `datetime` - Filter items by temporal extent using RFC3339 datetime strings:
  - Single datetime: `datetime=2022-01-01T00:00:00Z`
  - Date range: `datetime=2022-01-01T00:00:00Z/2023-01-01T00:00:00Z`
  - Open-ended ranges: `datetime=2022-01-01T00:00:00Z/..` or `datetime=../2023-01-01T00:00:00Z`

#### Other Parameters
- `limit` - Maximum number of items to return (default: 10)
- `bbox` - Spatial bounding box filter: `bbox=west,south,east,north`
- `ids` - Filter by specific item IDs: `ids=item1,item2,item3`

### Example Queries

```bash
# Get items from a specific time range
curl "http://localhost:8085/collections/io-lulc-9-class/items?datetime=2019-01-01T00:00:00Z/2023-01-01T00:00:00Z&limit=5"

# Get items with spatial filtering (bbox format: west,south,east,north)
curl "http://localhost:8085/collections/io-lulc-9-class/items?bbox=-66,-16,-60,-8"

# Get items with both spatial and temporal filters
curl "http://localhost:8085/collections/io-lulc-9-class/items?bbox=-66,-16,-60,-8&datetime=2020-01-01T00:00:00Z/2022-01-01T00:00:00Z"

# Search across all collections
curl -X POST "http://localhost:8085/search" \
  -H "Content-Type: application/json" \
  -d '{"datetime": "2019-01-01T00:00:00Z/2023-01-01T00:00:00Z", "limit": 10}'

# Search with bbox filter in POST request
curl -X POST "http://localhost:8085/search" \
  -H "Content-Type: application/json" \
  -d '{"bbox": [-66, -16, -60, -8], "limit": 10}'
```

## Configuration

### Environment Variables

#### Core Settings

- `STAC_FILE_PATH` (optional, default: `/app/stac_collections`):
  Directory containing STAC collection JSON files

- `PARQUET_URLS_JSON` (required): JSON object mapping collection IDs to Parquet file paths/URLs
  - Local file example: `{"io-lulc-9-class": "file:///app/stac_collections/io-lulc-9-class/io-lulc-9-class.parquet"}`
  - Relative path example: `{"io-lulc-9-class": "data/io-lulc-9-class.parquet"}` (uses storage backend)
  - S3 example: `{"landsat": "s3://public-bucket/path/landsat.parquet"}`
  - When running with Docker, use container paths (e.g., `/app/stac_collections/...`)

#### Storage Backend Settings

The storage backend configuration controls how GeoParquet files are accessed. The system supports local filesystem and Azure Blob Storage.

- `STAC_STORAGE_STORAGE_TYPE` (optional, default: `local`):
  Type of storage backend to use. Options: `local`, `azure_blob`

##### Local Storage Backend

When using local storage (default), files are accessed from the local filesystem.

- `STAC_STORAGE_LOCAL_DATA_PATH` (optional):
  Base directory for relative paths in `PARQUET_URLS_JSON`

Example configuration:
```bash
# .env file for local storage
STAC_STORAGE_STORAGE_TYPE=local
STAC_STORAGE_LOCAL_DATA_PATH=/data
PARQUET_URLS_JSON='{"collection1": "collection1.parquet", "collection2": "collection2.parquet"}'
```

##### Azure Blob Storage Backend

When using Azure Blob Storage, files are accessed from Azure. The backend supports multiple authentication methods.

- `STAC_STORAGE_AZURE_ACCOUNT_NAME` (required for Azure): Azure storage account name
- `STAC_STORAGE_AZURE_CONTAINER_NAME` (required for Azure): Azure blob container name
- `STAC_STORAGE_AZURE_AUTHENTICATION` (optional, default: `managed_identity`):
  Authentication method. Options:
  - `managed_identity`: Use Azure Managed Identity (recommended for production)
  - `sas_token`: Use a SAS (Shared Access Signature) token
  - `connection_string`: Use a connection string

###### Managed Identity Authentication (Recommended)

Best for production deployments in Azure.

```bash
# .env file for Azure with Managed Identity
STAC_STORAGE_STORAGE_TYPE=azure_blob
STAC_STORAGE_AZURE_ACCOUNT_NAME=mystorageaccount
STAC_STORAGE_AZURE_CONTAINER_NAME=stac-data
STAC_STORAGE_AZURE_AUTHENTICATION=managed_identity
PARQUET_URLS_JSON='{"collection1": "path/to/collection1.parquet"}'
```

###### SAS Token Authentication

Useful for temporary access or development.

- `STAC_STORAGE_AZURE_SAS_TOKEN` (required when using `sas_token` auth):
  SAS token for Azure Blob Storage

```bash
# .env file for Azure with SAS Token
STAC_STORAGE_STORAGE_TYPE=azure_blob
STAC_STORAGE_AZURE_ACCOUNT_NAME=mystorageaccount
STAC_STORAGE_AZURE_CONTAINER_NAME=stac-data
STAC_STORAGE_AZURE_AUTHENTICATION=sas_token
STAC_STORAGE_AZURE_SAS_TOKEN=sv=2022-11-02&ss=b&srt=co&sp=r&se=2024-12-31&...
PARQUET_URLS_JSON='{"collection1": "path/to/collection1.parquet"}'
```

###### Connection String Authentication

Alternative authentication method.

- `STAC_STORAGE_AZURE_CONNECTION_STRING` (required when using `connection_string` auth):
  Azure storage connection string

```bash
# .env file for Azure with Connection String
STAC_STORAGE_STORAGE_TYPE=azure_blob
STAC_STORAGE_AZURE_ACCOUNT_NAME=mystorageaccount
STAC_STORAGE_AZURE_CONTAINER_NAME=stac-data
STAC_STORAGE_AZURE_AUTHENTICATION=connection_string
STAC_STORAGE_AZURE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
PARQUET_URLS_JSON='{"collection1": "path/to/collection1.parquet"}'
```

**Note:** To use Azure Blob Storage, install the Azure dependencies:
```bash
pip install -e .[azure]
# or manually:
pip install azure-storage-blob azure-identity adlfs
```

## Development

### Running Tests

The project includes a Makefile with commands to run tests both locally and in Docker:

```bash
# Run tests locally (fastest)
make test-local

# Build and run tests in Docker
make test-build

# Run tests in existing Docker container
make test
```

### Azure Integration Testing

The project includes comprehensive integration tests for Azure Blob Storage that test real connectivity and operations:

```bash
# Deploy Azure test infrastructure
make azure-deploy

# Run Azure integration tests
make test-azure-integration

# Check Azure infrastructure status
make azure-status

# Clean up Azure resources
make azure-teardown
```

**Features:**
- Tests real Azure Blob Storage connectivity (not mocked)
- Supports both SAS token and managed identity authentication
- Verifies DuckDB can read from Azure URLs
- Infrastructure as Code using Azure Bicep templates
- Automated deployment and teardown scripts

For detailed setup and usage instructions, see [tests/integration/infrastructure/azure/README.md](tests/integration/infrastructure/azure/README.md).

### Running the Server

You can run the server either locally or in Docker:

```bash
# Run server locally on http://localhost:8000
make up-local

# Run server in Docker on http://localhost:8085
make up
```

### Pre-commit

Install [pre-commit](https://pre-commit.com/#install).

Prior to commit, run:

```shell
pre-commit run --all-files
```

## Build stac-fastapi.duckdb backend

```shell
docker compose build
```
  
## Running DuckDB API on localhost:8085

```shell
docker compose up
```

