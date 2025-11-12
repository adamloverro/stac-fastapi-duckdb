# STAC GeoParquet Validation Tool

This directory contains a diagnostic tool for validating STAC GeoParquet files against the STAC GeoParquet standard.

## Files

- `validate_stac_geoparquet.py` - Main validation script
- `validation-requirements.txt` - Python dependencies for the validation tool
- Other scripts for downloading and working with GeoParquet files

## Installation

Install the required dependencies for the validation tool:

```bash
pip install -r validation-requirements.txt
```

## Usage

### Validate All Files in stac_collections

```bash
python validate_stac_geoparquet.py
```

### Validate a Specific File

```bash
python validate_stac_geoparquet.py --file ../stac_collections/collections.parquet
```

### Verbose Output

```bash
python validate_stac_geoparquet.py --verbose
```

### JSON Output

```bash
python validate_stac_geoparquet.py --json
```

### Custom Directory

```bash
python validate_stac_geoparquet.py --directory /path/to/parquet/files
```

## What the Tool Validates

The validation tool checks for:

1. **File Structure**: Can the file be read as a valid Parquet file?
2. **Geometry Compliance**: Does the file contain valid geometry data?
3. **STAC Field Requirements**: Are required STAC fields present (id, geometry, bbox, type, stac_version)?
4. **STAC Item Structure**: Are items properly formatted as GeoJSON Features?
5. **Schema Validation**: Are column types appropriate for STAC GeoParquet?
6. **STAC GeoParquet Standard**: Does the file comply with the official STAC GeoParquet specification?

## Output

The tool provides:

- **Summary**: Overview of validation results for all files
- **Detailed Errors**: Specific issues that prevent compliance
- **Warnings**: Non-critical issues that should be addressed
- **Metadata**: Information about file structure and content
- **JSON Export**: Machine-readable validation results

## Exit Codes

- `0`: All files passed validation
- `1`: One or more files failed validation or an error occurred

## Dependencies

The validation tool requires:

- `stac-geoparquet`: Official STAC GeoParquet Python library
- `pandas`: Data manipulation
- `pyarrow`: Parquet file handling  
- `geopandas`: Geospatial data processing

See `validation-requirements.txt` for specific versions.