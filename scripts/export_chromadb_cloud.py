#!/usr/bin/env python3
"""
ChromaDB Cloud Export Script

Exports all records from ChromaDB Cloud to JSON file for migration to self-hosted instance.
Handles the 300-record GET quota by batching queries.

Usage:
    python3 scripts/export_chromadb_cloud.py --output chromadb_backup.json
"""

import argparse
import json
import sys
import os
from datetime import datetime
from typing import Dict, List

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.vector_db import VectorDBClient


def export_all_records(output_file: str = "chromadb_backup.json") -> Dict:
    """
    Export all records from ChromaDB Cloud to JSON.

    Args:
        output_file: Path to output JSON file

    Returns:
        Dictionary with export statistics
    """
    print("\n" + "=" * 70)
    print("📤 CHROMADB CLOUD EXPORT")
    print("=" * 70)

    try:
        # Step 1: Connect to ChromaDB Cloud
        print("\n1️⃣ Connecting to ChromaDB Cloud...")
        db = VectorDBClient()
        collection = db.collection
        print("   ✓ Connected successfully")

        # Step 2: Get total count
        print("\n2️⃣ Checking total record count...")
        total_count = collection.count()
        print(f"   Total records to export: {total_count}")

        if total_count == 0:
            print("   ⚠️  No records found in database")
            return {"total_records": 0, "exported": 0}

        # Step 3: Batch export with 300-record GET limit
        print("\n3️⃣ Exporting records in batches...")
        batch_size = 300
        offset = 0
        all_records = {
            "metadata": {
                "export_date": datetime.now().isoformat(),
                "collection_name": db.collection_name,
                "total_records": total_count,
                "embedding_model": db.model_name,
            },
            "records": []
        }

        batch_num = 1
        while offset < total_count:
            print(f"   Batch {batch_num}: Records {offset + 1}-{min(offset + batch_size, total_count)}")

            # Query batch
            batch = collection.get(
                include=["documents", "metadatas", "embeddings"],
                limit=batch_size,
                offset=offset
            )

            # Add to results
            for i in range(len(batch["ids"])):
                # Convert embedding to list if it's a numpy array
                embedding = batch["embeddings"][i]
                if hasattr(embedding, 'tolist'):
                    embedding = embedding.tolist()

                all_records["records"].append({
                    "id": batch["ids"][i],
                    "document": batch["documents"][i],
                    "metadata": batch["metadatas"][i],
                    "embedding": embedding
                })

            offset += batch_size
            batch_num += 1

        exported_count = len(all_records["records"])
        print(f"\n   ✓ Exported {exported_count} records in {batch_num - 1} batches")

        # Step 4: Save to JSON file
        print(f"\n4️⃣ Saving to {output_file}...")
        with open(output_file, 'w') as f:
            json.dump(all_records, f, indent=2)

        file_size_mb = os.path.getsize(output_file) / (1024 * 1024)
        print(f"   ✓ Saved {file_size_mb:.2f} MB")

        # Step 5: Verify export
        print("\n5️⃣ Verifying export...")
        with open(output_file, 'r') as f:
            verification = json.load(f)

        verified_count = len(verification["records"])
        if verified_count == total_count:
            print(f"   ✓ Verification passed: {verified_count} records")
        else:
            print(f"   ⚠️  Count mismatch: {verified_count} exported vs {total_count} in database")

        # Success summary
        print("\n" + "=" * 70)
        print("✅ EXPORT COMPLETE")
        print("=" * 70)
        print(f"\n📊 Export Summary:")
        print(f"   Total records: {total_count}")
        print(f"   Exported: {exported_count}")
        print(f"   File size: {file_size_mb:.2f} MB")
        print(f"   Output file: {output_file}")

        # Show stats
        stats = {}
        for record in all_records["records"]:
            client = record["metadata"].get("client_name", "Unknown")
            stats[client] = stats.get(client, 0) + 1

        print(f"\n   Records by client:")
        for client, count in sorted(stats.items(), key=lambda x: x[1], reverse=True):
            print(f"     - {client}: {count}")

        print("\n🚀 Next Step:")
        print("   Deploy ChromaDB on Railway, then run:")
        print(f"   python3 scripts/import_to_selfhosted.py --input {output_file}")
        print()

        return {
            "total_records": total_count,
            "exported": exported_count,
            "file_path": output_file,
            "file_size_mb": file_size_mb
        }

    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ EXPORT FAILED")
        print("=" * 70)
        print(f"\nError: {str(e)}")

        print("\n🔍 Troubleshooting:")
        print("   1. Check ChromaDB Cloud credentials in .env")
        print("   2. Verify network connectivity")
        print("   3. Check ChromaDB Cloud dashboard for service status")
        print()

        import traceback
        traceback.print_exc()

        return {"total_records": 0, "exported": 0, "error": str(e)}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Export all records from ChromaDB Cloud to JSON file"
    )
    parser.add_argument(
        "--output",
        default="chromadb_backup.json",
        help="Output JSON file path (default: chromadb_backup.json)"
    )
    args = parser.parse_args()

    result = export_all_records(args.output)

    # Exit with error code if export failed
    if result.get("error"):
        sys.exit(1)
    elif result["exported"] != result["total_records"]:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
