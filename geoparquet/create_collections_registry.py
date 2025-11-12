#!/usr/bin/env python
"""Create a collections registry GeoParquet file from existing collection.json files.

This script:
1. Scans the stac_collections directory for collection.json files
2. Extracts collection metadata
3. Creates a GeoParquet file with the collection registry
4. Adds collection metadata to each collection's STAC items GeoParquet file
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import geopandas as gpd
import pyarrow as pa
import pyarrow.parquet as pq
from shapely.geometry import box


def extract_collection_info(
    collection_json_path: Path,
    azure_account: Optional[str] = None,
    azure_container: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Extract collection information from a collection.json file.

    Args:
        collection_json_path: Path to collection.json file

    Returns:
        Dictionary with collection info or None if invalid
    """
    try:
        with open(collection_json_path, "r") as f:
            collection = json.load(f)

        collection_id = collection.get("id")
        if not collection_id:
            print(f"Warning: No 'id' field in {collection_json_path}")
            return None

        title = collection.get("title", collection_id)

        # Extract spatial extent (bbox)
        spatial_extent = collection.get("extent", {}).get("spatial", {})
        bbox_list = spatial_extent.get("bbox", [[]])
        if bbox_list and len(bbox_list) > 0:
            bbox = bbox_list[0]
            if len(bbox) >= 4:
                # Create a polygon geometry from bbox
                west, south, east, north = bbox[0], bbox[1], bbox[2], bbox[3]
            else:
                # Default to world bbox if invalid
                west, south, east, north = -180, -90, 180, 90
        else:
            # Default to world bbox if no bbox
            west, south, east, north = -180, -90, 180, 90

        # Extract temporal extent
        temporal_extent = collection.get("extent", {}).get("temporal", {})
        interval_list = temporal_extent.get("interval", [[]])
        if interval_list and len(interval_list) > 0:
            interval = interval_list[0]
            start_datetime = interval[0] if len(interval) > 0 else None
            end_datetime = interval[1] if len(interval) > 1 else None
        else:
            start_datetime = None
            end_datetime = None

        # Determine storage location - look for parquet file in same directory
        collection_dir = collection_json_path.parent
        parquet_file = collection_dir / f"{collection_id}.parquet"

        if parquet_file.exists():
            # Generate storage location based on deployment target
            if azure_account and azure_container:
                # Azure Blob Storage URL
                storage_location = f"collections/{collection_id}/{collection_id}.parquet"
            else:
                # Local relative path from stac_collections directory
                storage_location = f"{collection_id}/{collection_id}.parquet"
        else:
            print(f"Warning: No parquet file found for {collection_id}")
            storage_location = None

        return {
            "collection_id": collection_id,
            "title": title,
            "storage_location": storage_location,
            "bbox_west": west,
            "bbox_south": south,
            "bbox_east": east,
            "bbox_north": north,
            "temporal_start": start_datetime,
            "temporal_end": end_datetime,
            "created_time": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "geometry": box(west, south, east, north),  # Shapely polygon
        }

    except Exception as e:
        print(f"Error processing {collection_json_path}: {e}")
        return None


def create_collections_registry(
    stac_dir: Path,
    output_path: Path,
    azure_account: Optional[str] = None,
    azure_container: Optional[str] = None,
) -> None:
    """Create a collections registry GeoParquet file.

    Args:
        stac_dir: Path to stac_collections directory
        output_path: Path for output collections.parquet file
        azure_account: Optional Azure storage account name for Azure URLs
        azure_container: Optional Azure container name for Azure URLs
    """
    collections_info = []

    # Scan for collection.json files
    for collection_dir in stac_dir.iterdir():
        if not collection_dir.is_dir():
            continue

        collection_json = collection_dir / "collection.json"
        if not collection_json.exists():
            print(f"Skipping {collection_dir.name}: no collection.json found")
            continue

        info = extract_collection_info(collection_json, azure_account, azure_container)
        if info:
            collections_info.append(info)

    if not collections_info:
        print("ERROR: No valid collections found")
        sys.exit(1)

    # Create GeoDataFrame
    gdf = gpd.GeoDataFrame(collections_info, geometry="geometry", crs="EPSG:4326")

    # Reorder columns for better readability
    column_order = [
        "collection_id",
        "title",
        "storage_location",
        "bbox_west",
        "bbox_south",
        "bbox_east",
        "bbox_north",
        "temporal_start",
        "temporal_end",
        "created_time",
        "geometry",
    ]
    gdf = gdf[column_order]

    # Write to GeoParquet
    gdf.to_parquet(output_path, index=False)
    print(f"\nCreated collections registry: {output_path}")
    print(f"Collections: {len(gdf)}")
    for _, row in gdf.iterrows():
        print(f"  - {row['collection_id']}: {row['title']}")


def add_collection_metadata_to_parquet(
    collection_json_path: Path, parquet_path: Path
) -> None:
    """Add collection metadata to a STAC items GeoParquet file.

    This follows the STAC GeoParquet specification by storing collection
    metadata in the Parquet file's schema metadata.

    Args:
        collection_json_path: Path to collection.json file
        parquet_path: Path to STAC items parquet file
    """
    try:
        # Read collection JSON
        with open(collection_json_path, "r") as f:
            collection = json.load(f)

        # Read existing parquet file
        table = pq.read_table(parquet_path)

        # Get existing metadata or create new
        existing_metadata = table.schema.metadata or {}

        # Convert existing metadata from bytes to dict if needed
        metadata_dict = {
            k.decode("utf-8")
            if isinstance(k, bytes)
            else k: v.decode("utf-8")
            if isinstance(v, bytes)
            else v
            for k, v in existing_metadata.items()
        }

        # Add collection metadata under 'stac:collection' key
        # This follows the STAC GeoParquet spec
        metadata_dict["stac:collection"] = json.dumps(collection)

        # Create new schema with updated metadata
        new_metadata = {
            k.encode("utf-8")
            if isinstance(k, str)
            else k: v.encode("utf-8")
            if isinstance(v, str)
            else v
            for k, v in metadata_dict.items()
        }
        new_schema = table.schema.with_metadata(new_metadata)

        # Create new table with updated schema
        new_table = pa.Table.from_arrays(table.columns, schema=new_schema)

        # Write back to parquet
        pq.write_table(new_table, parquet_path)
        print(f"Added collection metadata to {parquet_path}")

    except Exception as e:
        print(f"Error adding metadata to {parquet_path}: {e}")


def main() -> None:
    """Create collections registry and update parquet files."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Create a collections registry GeoParquet file"
    )
    parser.add_argument(
        "--stac-dir",
        type=Path,
        help="Path to stac_collections directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Path for output collections.parquet file",
    )
    parser.add_argument(
        "--azure-account",
        type=str,
        help="Azure storage account name (for Azure URL generation)",
    )
    parser.add_argument(
        "--azure-container",
        type=str,
        help="Azure container name (for Azure URL generation)",
    )

    args = parser.parse_args()

    # Determine paths
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    stac_dir = args.stac_dir if args.stac_dir else repo_root / "stac_collections"
    output_path = (
        args.output if args.output else stac_dir / "collections.parquet"
    )

    print(f"Scanning collections in: {stac_dir}")
    print(f"Output will be: {output_path}")
    if args.azure_account:
        print(f"Generating Azure URLs for account: {args.azure_account}")
    print()

    # Create collections registry
    create_collections_registry(
        stac_dir, output_path, args.azure_account, args.azure_container
    )

    # Add collection metadata to each collection's parquet file
    print("\nAdding collection metadata to STAC item parquet files...")
    for collection_dir in stac_dir.iterdir():
        if not collection_dir.is_dir():
            continue

        collection_json = collection_dir / "collection.json"
        if not collection_json.exists():
            continue

        # Look for parquet file
        collection_id = collection_dir.name
        parquet_file = collection_dir / f"{collection_id}.parquet"

        if parquet_file.exists():
            add_collection_metadata_to_parquet(collection_json, parquet_file)
        else:
            print(f"Skipping {collection_id}: no parquet file found")

    print("\nDone!")


if __name__ == "__main__":
    main()
