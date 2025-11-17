#!/usr/bin/env python3
"""
ChromaDB Self-Hosted Import Script

Imports records from exported JSON file into self-hosted ChromaDB instance.

Usage:
    python3 scripts/import_to_selfhosted.py --input chromadb_backup.json
"""

import argparse
import json
import sys
import os
import chromadb
from datetime import datetime
from typing import Dict, List
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

load_dotenv()


def import_records(input_file: str) -> Dict:
    """
    Import all records from JSON backup into self-hosted ChromaDB.

    Args:
        input_file: Path to JSON backup file

    Returns:
        Dictionary with import statistics
    """
    print("\n" + "=" * 70)
    print("📥 CHROMADB SELF-HOSTED IMPORT")
    print("=" * 70)

    try:
        # Step 1: Load backup file
        print(f"\n1️⃣ Loading backup from {input_file}...")
        if not os.path.exists(input_file):
            print(f"   ❌ File not found: {input_file}")
            return {"error": "File not found"}

        with open(input_file, "r") as f:
            backup_data = json.load(f)

        total_records = len(backup_data["records"])
        print(f"   ✓ Loaded {total_records} records")
        print(f"   Export date: {backup_data['metadata']['export_date']}")
        print(f"   Collection: {backup_data['metadata']['collection_name']}")

        # Step 2: Connect to self-hosted ChromaDB
        print("\n2️⃣ Connecting to self-hosted ChromaDB...")
        chroma_host = os.getenv("CHROMA_HOST", "localhost")
        chroma_port = int(os.getenv("CHROMA_PORT", "8000"))
        chroma_ssl = os.getenv("CHROMA_SSL", "false").lower() == "true"
        chroma_tenant = os.getenv("CHROMA_TENANT", "default_tenant")
        chroma_database = os.getenv("CHROMA_DATABASE", "default_database")

        print(f"   Host: {chroma_host}")
        print(f"   Port: {chroma_port}")
        print(f"   SSL: {chroma_ssl}")
        print(f"   Tenant: {chroma_tenant}")
        print(f"   Database: {chroma_database}")

        # Build headers with optional auth token
        headers = {}
        auth_token = os.getenv("CHROMA_AUTH_TOKEN")
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
            print(f"   Auth: Token provided")

        client = chromadb.HttpClient(
            host=chroma_host,
            port=chroma_port,
            ssl=chroma_ssl,
            headers=headers if headers else None,
            tenant=chroma_tenant,
            database=chroma_database,
        )

        # Test connection
        client.heartbeat()
        print("   ✓ Connected successfully")

        # Step 3: Get or create collection
        print("\n3️⃣ Setting up collection...")
        collection_name = backup_data["metadata"]["collection_name"]

        # Check if collection exists
        existing_collections = [col.name for col in client.list_collections()]
        if collection_name in existing_collections:
            print(f"   ⚠️  Collection '{collection_name}' already exists")
            collection = client.get_collection(collection_name)
            print(
                f"   Existing record count: {collection.count()}"
            )
            response = input("   Delete and recreate? (y/N): ").strip().lower()
            if response == "y":
                client.delete_collection(collection_name)
                print(f"   ✓ Deleted existing collection")
                # Create new collection with metadata (like test_railway_live.py)
                collection = client.create_collection(
                    name=collection_name,
                    metadata={
                        "description": "CRO audit issues - imported from backup",
                        "imported_at": datetime.now().isoformat()
                    }
                )
                print(f"   ✓ Created new collection")
            else:
                print(f"   ✓ Using existing collection")
        else:
            # Create new collection with metadata (like test_railway_live.py)
            collection = client.create_collection(
                name=collection_name,
                metadata={
                    "description": "CRO audit issues - imported from backup",
                    "imported_at": datetime.now().isoformat()
                }
            )
            print(f"   ✓ Created collection: {collection_name}")

        # Step 4: Import records in batches
        print("\n4️⃣ Importing records...")
        batch_size = 100  # Smaller batches for better error handling
        imported_count = 0
        failed_count = 0

        for batch_start in range(0, total_records, batch_size):
            batch_end = min(batch_start + batch_size, total_records)
            batch_records = backup_data["records"][batch_start:batch_end]

            # Prepare batch data
            ids = [r["id"] for r in batch_records]
            documents = [r["document"] for r in batch_records]
            metadatas = [r["metadata"] for r in batch_records]
            embeddings = [r["embedding"] for r in batch_records]

            try:
                collection.add(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,
                    embeddings=embeddings,
                )
                imported_count += len(batch_records)
                print(
                    f"   Batch {batch_start // batch_size + 1}: Imported {batch_start + 1}-{batch_end}"
                )

            except Exception as batch_error:
                print(
                    f"   ❌ Batch {batch_start // batch_size + 1} failed: {str(batch_error)}"
                )
                failed_count += len(batch_records)

        print(f"\n   ✓ Import complete: {imported_count}/{total_records} records")
        if failed_count > 0:
            print(f"   ⚠️  Failed: {failed_count} records")

        # Step 5: Verify import
        print("\n5️⃣ Verifying import...")
        final_count = collection.count()
        print(f"   Final record count: {final_count}")

        if final_count == total_records:
            print(f"   ✓ Verification passed!")
        else:
            print(
                f"   ⚠️  Count mismatch: {final_count} imported vs {total_records} in backup"
            )

        # Success summary
        print("\n" + "=" * 70)
        print("✅ IMPORT COMPLETE")
        print("=" * 70)
        print(f"\n📊 Import Summary:")
        print(f"   Total records: {total_records}")
        print(f"   Imported: {imported_count}")
        print(f"   Failed: {failed_count}")
        print(f"   Final count: {final_count}")

        # Show stats
        stats = {}
        for record in backup_data["records"]:
            client_name = record["metadata"].get("client_name", "Unknown")
            stats[client_name] = stats.get(client_name, 0) + 1

        print(f"\n   Records by client:")
        for client, count in sorted(stats.items(), key=lambda x: x[1], reverse=True):
            print(f"     - {client}: {count}")

        print("\n🚀 Next Step:")
        print("   Update utils/vector_db.py to use HttpClient permanently")
        print("   Then run full ingestion:")
        print("   python3 scripts/ingest_audits.py --local-dir sample_audits/")
        print()

        return {
            "total_records": total_records,
            "imported": imported_count,
            "failed": failed_count,
            "final_count": final_count,
        }

    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ IMPORT FAILED")
        print("=" * 70)
        print(f"\nError: {str(e)}")

        print("\n🔍 Troubleshooting:")
        print("   1. Check ChromaDB is running (Railway deployment)")
        print("   2. Verify CHROMA_HOST and CHROMA_PORT in .env")
        print("   3. Test connection: curl http://<host>:<port>/api/v1/heartbeat")
        print("   4. Check auth token if required")
        print()

        import traceback

        traceback.print_exc()

        return {"error": str(e)}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Import records from JSON backup into self-hosted ChromaDB"
    )
    parser.add_argument(
        "--input",
        default="chromadb_backup.json",
        help="Input JSON backup file (default: chromadb_backup.json)",
    )
    args = parser.parse_args()

    result = import_records(args.input)

    # Exit with error code if import failed
    if result.get("error"):
        sys.exit(1)
    elif result.get("failed", 0) > 0:
        print("⚠️  Some records failed to import")
        sys.exit(1)
    elif result.get("final_count", 0) != result.get("total_records", 0):
        print("⚠️  Final count doesn't match expected")
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
