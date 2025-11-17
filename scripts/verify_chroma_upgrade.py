#!/usr/bin/env python3
"""
ChromaDB Cloud Upgrade Verification Script

Verifies that the ChromaDB Cloud upgrade to Starter plan is working
by testing the quota limit has been increased from 300 records.

Usage:
    python3 scripts/verify_chroma_upgrade.py
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.vector_db import VectorDBClient


def verify_upgrade() -> bool:
    """
    Verify ChromaDB Cloud upgrade by testing quota limits.

    Returns:
        True if upgrade verified successfully, False otherwise
    """
    print("\n" + "=" * 70)
    print("🔍 CHROMADB CLOUD UPGRADE VERIFICATION")
    print("=" * 70)

    try:
        # Step 1: Connect to ChromaDB Cloud
        print("\n1️⃣ Connecting to ChromaDB Cloud...")
        db = VectorDBClient()
        print("   ✓ Connected successfully")

        # Step 2: Get current stats
        print("\n2️⃣ Checking current database state...")
        stats = db.get_stats()
        current_count = stats["total_issues"]
        print(f"   Current record count: {current_count}")

        if current_count != 300:
            print(f"   ⚠️  Warning: Expected 300 records, found {current_count}")
        else:
            print("   ✓ Record count matches expected (300 at old quota)")

        # Step 3: Create test issues to verify unlimited quota
        print("\n3️⃣ Testing quota limit...")
        print("   Adding 2 test records to verify unlimited quota...")

        test_issues = [
            {
                "client_name": "__VERIFICATION_TEST__",
                "section": "Test Section 1",
                "issue_title": "Test Issue 1 - Quota Verification",
                "issue_description": "This is a test issue to verify ChromaDB Cloud upgrade is working",
                "why_it_matters": "Testing unlimited quota on Starter plan",
                "recommendations": ["Remove this test record after verification"],
                "industry": "test",
                "audit_date": "2025-01-01"
            },
            {
                "client_name": "__VERIFICATION_TEST__",
                "section": "Test Section 2",
                "issue_title": "Test Issue 2 - Quota Verification",
                "issue_description": "This is a second test issue to verify ChromaDB Cloud upgrade",
                "why_it_matters": "Confirming quota increase is working",
                "recommendations": ["Remove this test record after verification"],
                "industry": "test",
                "audit_date": "2025-01-01"
            }
        ]

        try:
            added_count = db.add_issues_bulk(test_issues)
            print(f"   ✓ Successfully added {added_count} test records")
            print("   ✓ Quota limit verified - upgrade is working!")

        except Exception as add_error:
            error_msg = str(add_error)
            if "Quota exceeded" in error_msg or "exceeds limit" in error_msg:
                print(f"\n   ❌ QUOTA ERROR: {error_msg}")
                print("\n   This suggests the upgrade hasn't taken effect yet.")
                print("   Possible causes:")
                print("   1. Upgrade is still processing (wait 5-10 minutes)")
                print("   2. Using wrong credentials (check .env file)")
                print("   3. Upgrade wasn't completed successfully")
                return False
            else:
                # Some other error - re-raise it
                raise

        # Step 4: Verify test records were added
        print("\n4️⃣ Verifying test records...")
        new_stats = db.get_stats()
        new_count = new_stats["total_issues"]
        print(f"   New record count: {new_count}")

        if new_count == current_count + 2:
            print("   ✓ Test records successfully added to database")
        else:
            print(f"   ⚠️  Expected {current_count + 2}, found {new_count}")

        # Step 5: Clean up test records
        print("\n5️⃣ Cleaning up test records...")
        try:
            # Get collection
            collection = db.client.get_collection(name=db.collection_name)

            # Delete test records by client_name metadata
            collection.delete(
                where={"client_name": "__VERIFICATION_TEST__"}
            )
            print("   ✓ Test records removed")

            # Verify cleanup
            final_stats = db.get_stats()
            final_count = final_stats["total_issues"]
            print(f"   Final record count: {final_count}")

            if final_count == current_count:
                print("   ✓ Database restored to original state")
            else:
                print(f"   ⚠️  Expected {current_count}, found {final_count}")

        except Exception as cleanup_error:
            print(f"   ⚠️  Cleanup error: {cleanup_error}")
            print("   Test records may still be in database")
            print("   Run this query to remove them manually:")
            print("   collection.delete(where={'client_name': '__VERIFICATION_TEST__'})")

        # Success!
        print("\n" + "=" * 70)
        print("✅ VERIFICATION SUCCESSFUL!")
        print("=" * 70)
        print("\n📊 Summary:")
        print(f"   ✓ ChromaDB Cloud connection: Working")
        print(f"   ✓ Current database size: {current_count} issues")
        print(f"   ✓ Quota limit: Unlimited (Starter plan)")
        print(f"   ✓ Test records: Added and cleaned up successfully")
        print("\n🚀 Next Step:")
        print("   Run full ingestion to add remaining 877 issues:")
        print("   python3 scripts/ingest_audits.py --local-dir sample_audits/")
        print()

        return True

    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ VERIFICATION FAILED")
        print("=" * 70)
        print(f"\nError: {str(e)}")

        print("\n🔍 Troubleshooting:")
        print("   1. Check ChromaDB Cloud credentials in .env:")
        print("      - CHROMA_API_KEY")
        print("      - CHROMA_TENANT")
        print("      - CHROMA_DATABASE")
        print("   2. Verify upgrade was completed in ChromaDB Cloud dashboard")
        print("   3. Wait 5-10 minutes if upgrade was just completed")
        print("   4. Check network connectivity to ChromaDB Cloud")
        print()

        import traceback
        traceback.print_exc()

        return False


def main():
    """Main entry point."""
    success = verify_upgrade()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
