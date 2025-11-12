#!/usr/bin/env python3
"""STAC GeoParquet Validation Tool.

A diagnostic tool to validate STAC GeoParquet files against the STAC GeoParquet standard.
This script scans the /stac_collections directory for .parquet files and validates them
for compliance with STAC GeoParquet specifications.

Usage:
    python validate_stac_geoparquet.py [--file path/to/file.parquet] [--verbose] [--json]

Examples:
    # Validate all parquet files in stac_collections
    python validate_stac_geoparquet.py

    # Validate a specific file
    python validate_stac_geoparquet.py --file ../stac_collections/collections.parquet

    # Verbose output with detailed validation results
    python validate_stac_geoparquet.py --verbose

    # Output results as JSON
    python validate_stac_geoparquet.py --json
"""

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List

try:
    import geopandas as gpd
    import pyarrow.parquet as pq
    from stac_geoparquet.stac_geoparquet import to_item_collection
except ImportError as e:
    print(f"Error: Missing required dependencies. Please install: {e}")
    print("Try: pip install stac-geoparquet pandas pyarrow geopandas")
    sys.exit(1)

# Suppress warnings for cleaner output unless verbose mode is enabled
warnings.filterwarnings("ignore")


class STACGeoParquetValidator:
    """Validator for STAC GeoParquet files."""

    def __init__(self, verbose: bool = False) -> None:
        """Initialize the validator.

        Args:
            verbose: Enable verbose output
        """
        self.verbose = verbose
        self.results: List[Dict[str, Any]] = []

    def _print_verbose(self, message: str) -> None:
        """Print message only in verbose mode."""
        if self.verbose:
            print(message)

    def validate_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Validate a single STAC GeoParquet file.

        Args:
            file_path: Path to the parquet file

        Returns:
            Dictionary containing validation results
        """
        result: Dict[str, Any] = {
            "file": str(file_path),
            "valid": False,
            "errors": [],
            "warnings": [],
            "metadata": {},
            "schema_validation": None,
            "stac_compliance": None,
        }

        self._print_verbose(f"\n🔍 Validating: {file_path}")

        try:
            # Check if file exists and is readable
            if not file_path.exists():
                result["errors"].append(f"File does not exist: {file_path}")
                return result

            if not file_path.is_file():
                result["errors"].append(f"Path is not a file: {file_path}")
                return result

            # Read parquet metadata
            try:
                parquet_file = pq.ParquetFile(file_path)
                metadata = parquet_file.metadata
                schema = parquet_file.schema_arrow

                result["metadata"] = {
                    "num_rows": metadata.num_rows,
                    "num_columns": len(schema),
                    "file_size_bytes": file_path.stat().st_size,
                    "schema_fields": [field.name for field in schema],
                }

                self._print_verbose(
                    f"  📊 Rows: {metadata.num_rows}, Columns: {len(schema)}"
                )

            except Exception as e:
                result["errors"].append(f"Failed to read parquet metadata: {str(e)}")
                return result

            # Read the data using GeoPandas to check for geometry
            try:
                gdf = gpd.read_parquet(file_path)

                # Check for geometry column
                if gdf.geometry is None:
                    result["errors"].append("No geometry column found")
                elif len(gdf) == 0:
                    result["errors"].append("No data in file")
                elif gdf.geometry.isna().all():
                    result["errors"].append("No valid geometries found")
                else:
                    self._print_verbose(f"  🌍 Geometry column: {gdf.geometry.name}")
                    result["metadata"]["geometry_column"] = gdf.geometry.name
                    result["metadata"]["geometry_types"] = list(
                        gdf.geometry.geom_type.unique()
                    )

                # Check for required STAC fields
                required_stac_fields = [
                    "id",
                    "geometry",
                    "bbox",
                    "type",
                    "stac_version",
                ]
                missing_fields = []

                for field in required_stac_fields:
                    if field not in gdf.columns:
                        missing_fields.append(field)

                if missing_fields:
                    result["errors"].append(f"Missing STAC fields: {missing_fields}")
                else:
                    self._print_verbose("  ✅ All required STAC fields present")

                # Check STAC item structure
                if "type" in gdf.columns:
                    item_types = gdf["type"].unique()
                    if len(item_types) == 1 and item_types[0] == "Feature":
                        self._print_verbose("  ✅ All items have correct type 'Feature'")
                    else:
                        result["errors"].append(
                            f"Unexpected item types found: {item_types}"
                        )
                else:
                    result["warnings"].append(
                        "Missing 'type' column for STAC items; not required for STAC Items in GeoParquet"
                    )

                # Check for STAC version consistency
                if "stac_version" in gdf.columns:
                    stac_versions = gdf["stac_version"].unique()
                    if len(stac_versions) == 1:
                        self._print_verbose(f"  📋 STAC version: {stac_versions[0]}")
                        result["metadata"]["stac_version"] = stac_versions[0]
                    else:
                        result["warnings"].append(
                            f"Multiple STAC versions found: {stac_versions}"
                        )

            except Exception as e:
                result["errors"].append(f"Failed to read parquet data: {str(e)}")
                return result

            # Use stac-geoparquet validation if available
            try:
                # Read GeoParquet to geodataframe
                gdf = gpd.read_parquet(file_path)

                # If successful, try to convert to item collection to validate STAC compliance
                item_collection = to_item_collection(gdf)

                # Try to read as STAC GeoParquet and convert to geodataframe
                # gdf_from_stac = to_geodataframe(str(file_path))

                result["stac_compliance"] = {
                    "valid": True,
                    "details": f"Successfully converted to STAC ItemCollection with {len(item_collection)} items",
                    "item_count": len(item_collection)
                    if hasattr(item_collection, "__len__")
                    else "unknown",
                }

                self._print_verbose("  ✅ STAC GeoParquet validation passed")

            except Exception as e:
                result["errors"].append(f"STAC GeoParquet validation failed: {str(e)}")
                result["stac_compliance"] = {"valid": False, "details": str(e)}

            # Schema validation
            try:
                # Check for proper column types
                expected_types = {
                    "id": ["string", "large_string"],
                    "type": ["string", "large_string"],
                    "stac_version": ["string", "large_string"],
                    "bbox": ["list"],
                    "geometry": ["binary"],  # WKB format
                }

                schema_issues = []
                for field_name, expected in expected_types.items():
                    if field_name in [field.name for field in schema]:
                        field_type = str(schema.field(field_name).type)
                        if not any(
                            exp_type in field_type.lower() for exp_type in expected
                        ):
                            schema_issues.append(
                                f"{field_name}: expected {expected}, got {field_type}"
                            )

                if schema_issues:
                    result["warnings"].extend(schema_issues)
                else:
                    self._print_verbose("  ✅ Schema types are valid")

                result["schema_validation"] = {
                    "valid": len(schema_issues) == 0,
                    "issues": schema_issues,
                }

            except Exception as e:
                result["errors"].append(f"Schema validation failed: {str(e)}")

            # Overall validation result
            result["valid"] = len(result["errors"]) == 0

            if result["valid"]:
                self._print_verbose("  🎉 File validation passed!")
            else:
                self._print_verbose("  ❌ File validation failed!")

        except Exception as e:
            result["errors"].append(f"Unexpected error during validation: {str(e)}")

        return result

    def find_parquet_files(self, directory: Path) -> List[Path]:
        """Find all .parquet files in the given directory and subdirectories."""
        parquet_files = []

        try:
            for file_path in directory.rglob("*.parquet"):
                if file_path.is_file():
                    parquet_files.append(file_path)
        except Exception as e:
            print(f"Error scanning directory {directory}: {e}")

        return sorted(parquet_files)

    def validate_directory(self, directory: Path) -> List[Dict[str, Any]]:
        """Validate all parquet files in a directory."""
        parquet_files = self.find_parquet_files(directory)

        if not parquet_files:
            print(f"No .parquet files found in {directory}")
            return []

        print(f"Found {len(parquet_files)} parquet file(s) to validate:")
        for file_path in parquet_files:
            print(f"  - {file_path}")

        results = []
        for file_path in parquet_files:
            result = self.validate_file(file_path)
            results.append(result)
            self.results.append(result)

        return results


def print_summary(results: List[Dict[str, Any]], json_output: bool = False):
    """Print a summary of validation results."""
    if json_output:
        print(json.dumps(results, indent=2))
        return

    if not results:
        print("No files validated.")
        return

    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)

    total_files = len(results)
    valid_files = sum(1 for r in results if r["valid"])

    print(f"Total files validated: {total_files}")
    print(f"Valid files: {valid_files}")
    print(f"Invalid files: {total_files - valid_files}")

    if valid_files == total_files:
        print("\n🎉 All files are valid STAC GeoParquet files!")
    else:
        print(f"\n⚠️  {total_files - valid_files} file(s) have validation issues:")

        for result in results:
            if not result["valid"]:
                print(f"\n❌ {result['file']}:")
                for error in result["errors"]:
                    print(f"   Error: {error}")
                for warning in result["warnings"]:
                    print(f"   Warning: {warning}")

    # Print warnings for valid files too
    valid_files_with_warnings = [r for r in results if r["valid"] and r["warnings"]]
    if valid_files_with_warnings:
        print(f"\n⚠️  {len(valid_files_with_warnings)} valid file(s) have warnings:")
        for result in valid_files_with_warnings:
            print(f"\n🟡 {result['file']}:")
            for warning in result["warnings"]:
                print(f"   Warning: {warning}")


def main() -> None:
    """Execute the validation tool."""
    parser = argparse.ArgumentParser(
        description="Validate STAC GeoParquet files for compliance with STAC GeoParquet standard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--file", type=Path, help="Path to a specific parquet file to validate"
    )

    parser.add_argument(
        "--directory",
        type=Path,
        default=Path(__file__).parent.parent / "stac_collections",
        help="Directory to scan for parquet files (default: ../stac_collections)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output with detailed validation information",
    )

    parser.add_argument(
        "--json", action="store_true", help="Output results in JSON format"
    )

    args = parser.parse_args()

    # Enable warnings in verbose mode
    if args.verbose:
        warnings.filterwarnings("default")

    validator = STACGeoParquetValidator(verbose=args.verbose)

    print("🔍 STAC GeoParquet Validation Tool")
    print("=" * 40)

    if args.file:
        # Validate single file
        if not args.file.exists():
            print(f"Error: File not found: {args.file}")
            sys.exit(1)

        result = validator.validate_file(args.file)
        results = [result]
    else:
        # Validate directory
        if not args.directory.exists():
            print(f"Error: Directory not found: {args.directory}")
            sys.exit(1)

        print(f"Scanning directory: {args.directory}")
        results = validator.validate_directory(args.directory)

    print_summary(results, json_output=args.json)

    # Exit with error code if any files failed validation
    invalid_count = sum(1 for r in results if not r["valid"])
    if invalid_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
