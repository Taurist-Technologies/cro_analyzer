#!/usr/bin/env python3
"""
Bulk Audit Ingestion Script

Downloads audit documents from Google Drive, parses them, and ingests
into ChromaDB vector database for historical pattern matching.

Usage:
    python3 scripts/ingest_audits.py --folder-id <GOOGLE_DRIVE_FOLDER_ID>
    python3 scripts/ingest_audits.py --local-dir sample_audits/
"""

import argparse
import os
import sys
from datetime import datetime
from typing import List, Dict

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.google_drive_client import GoogleDriveClient
from utils.document_parser import DocumentParser
from utils.vector_db import VectorDBClient


# Industry mapping based on client name or audit content
INDUSTRY_MAPPING = {
    "mifold": "e-commerce",
    "annabella": "e-commerce",
    "enso": "b2b",
    "bubble": "e-commerce",
    "hiccapop": "e-commerce",
    "omnilux": "e-commerce",
    "beam": "e-commerce",
    "laneige": "e-commerce",
    "momcozy": "e-commerce",
    "solawave": "e-commerce",
    "humann": "e-commerce",
}


def detect_industry(client_name: str, content: str = "") -> str:
    """
    Detect industry from client name or audit content.

    Args:
        client_name: Name of the client
        content: Audit overview text

    Returns:
        Industry string (e-commerce, b2b, saas, etc.)
    """
    client_lower = client_name.lower()

    # Check exact matches
    for key, industry in INDUSTRY_MAPPING.items():
        if key in client_lower:
            return industry

    # Check content for keywords
    content_lower = content.lower()
    if any(
        word in content_lower
        for word in [
            "shopify",
            "product page",
            "cart",
            "checkout",
            "ecommerce",
            "e-commerce",
        ]
    ):
        return "e-commerce"
    elif any(
        word in content_lower
        for word in ["b2b", "enterprise", "lead generation", "case studies"]
    ):
        return "b2b"
    elif any(
        word in content_lower for word in ["saas", "software", "subscription", "trial"]
    ):
        return "saas"

    return "unknown"


def ingest_from_google_drive(folder_id: str, temp_dir: str = "temp_audits") -> int:
    """
    Download audits from Google Drive and ingest into vector DB.

    Args:
        folder_id: Google Drive folder ID
        temp_dir: Temporary directory for downloaded files

    Returns:
        Number of audits successfully ingested
    """
    print("\n" + "=" * 60)
    print("📥 GOOGLE DRIVE INGESTION")
    print("=" * 60)

    # Initialize clients
    print("\n1️⃣ Initializing Google Drive client...")
    drive_client = GoogleDriveClient(
        credentials_path=os.getenv("GOOGLE_CREDENTIALS_PATH"), use_service_account=True
    )

    print("\n2️⃣ Downloading audits from Google Drive...")
    docx_files = drive_client.bulk_download_folder_as_docx(
        folder_id=folder_id, output_dir=temp_dir
    )

    if not docx_files:
        print("❌ No files downloaded. Check folder ID and permissions.")
        return 0

    print(f"\n3️⃣ Processing {len(docx_files)} audits...")
    return ingest_from_local_dir(temp_dir)


def ingest_from_local_dir(directory: str) -> int:
    """
    Ingest audits from local directory of DOCX files.

    Args:
        directory: Path to directory containing DOCX files

    Returns:
        Number of audits successfully ingested
    """
    print("\n" + "=" * 60)
    print("📁 LOCAL DIRECTORY INGESTION")
    print("=" * 60)

    # Find all DOCX files
    docx_files = []
    for filename in os.listdir(directory):
        if filename.endswith(".docx") and not filename.startswith("~"):
            docx_files.append(os.path.join(directory, filename))

    if not docx_files:
        print(f"❌ No DOCX files found in {directory}")
        return 0

    print(f"Found {len(docx_files)} DOCX files")

    # Initialize vector database
    print("\n1️⃣ Initializing ChromaDB vector database...")
    db = VectorDBClient()

    # Get initial stats
    initial_stats = db.get_stats()
    initial_count = initial_stats["total_issues"]
    print(f"  Current database size: {initial_count} issues")

    # Process each audit
    total_issues_added = 0
    successful_audits = 0

    for i, docx_path in enumerate(docx_files, 1):
        filename = os.path.basename(docx_path)
        print(f"\n2️⃣ [{i}/{len(docx_files)}] Processing: {filename}")

        try:
            # Parse document
            parser = DocumentParser(docx_path)
            audit = parser.parse()

            # Detect industry
            industry = detect_industry(audit.client_name, audit.overview)
            print(f"  Industry: {industry}")

            # Prepare issues for bulk insert
            issues_to_add = []
            audit_date = datetime.now().strftime("%Y-%m-%d")

            for section in audit.sections:
                for issue in section.issues:
                    issues_to_add.append(
                        {
                            "client_name": audit.client_name,
                            "section": section.title,
                            "issue_title": issue["title"],
                            "issue_description": issue.get("description", ""),
                            "why_it_matters": issue.get("why_it_matters", ""),
                            "recommendations": issue.get("recommendations", []),
                            "industry": industry,
                            "audit_date": audit_date,
                        }
                    )

            # Bulk add to vector DB
            if issues_to_add:
                count = db.add_issues_bulk(issues_to_add)
                total_issues_added += count
                successful_audits += 1
                print(f"  ✓ Added {count} issues from {len(audit.sections)} sections")
            else:
                print(f"  ⚠ No issues found in audit")

        except Exception as e:
            print(f"  ✗ Error processing {filename}: {str(e)}")
            import traceback

            traceback.print_exc()
            continue

    # Final stats
    print("\n" + "=" * 60)
    print("✅ INGESTION COMPLETE")
    print("=" * 60)
    print(f"Audits processed: {successful_audits}/{len(docx_files)}")
    print(f"Total issues added: {total_issues_added}")

    final_stats = db.get_stats()
    print(f"\n📊 Database Stats:")
    print(f"  Total issues: {final_stats['total_issues']}")
    print(f"  Issues by section:")
    for section, count in sorted(
        final_stats["sections"].items(), key=lambda x: x[1], reverse=True
    ):
        print(f"    - {section}: {count}")
    print(f"  Issues by industry:")
    for industry, count in sorted(
        final_stats["industries"].items(), key=lambda x: x[1], reverse=True
    ):
        print(f"    - {industry}: {count}")

    return successful_audits


def test_queries(db: VectorDBClient):
    """
    Run test queries to verify data quality.

    Args:
        db: VectorDBClient instance
    """
    print("\n" + "=" * 60)
    print("🔍 TESTING QUERIES")
    print("=" * 60)

    test_cases = [
        {
            "query": "Navigation is too complex and confusing",
            "section": "Navigation",
            "description": "Testing navigation complexity issues",
        },
        {
            "query": "Hero section lacks clear value proposition",
            "section": "Home Page",
            "description": "Testing hero/value prop issues",
        },
        {
            "query": "Product images are too small and low quality",
            "section": "Product Page",
            "description": "Testing product page issues",
        },
        {
            "query": "Form has too many required fields causing friction",
            "section": None,
            "description": "Testing form optimization issues (any section)",
        },
    ]

    for i, test in enumerate(test_cases, 1):
        print(f"\n{i}. {test['description']}")
        print(f"   Query: \"{test['query']}\"")
        if test["section"]:
            print(f"   Section: {test['section']}")

        similar = db.query_similar_issues(
            query_text=test["query"], section=test["section"], n_results=3
        )

        if similar:
            print(f"   Found {len(similar)} similar issues:")
            for j, issue in enumerate(similar, 1):
                print(f"\n   [{j}] Similarity: {issue['similarity']:.1%}")
                print(f"       Title: {issue['metadata']['issue_title']}")
                print(f"       Client: {issue['metadata']['client_name']}")
                print(f"       Section: {issue['metadata']['section']}")
                print(f"       Recs: {issue['metadata']['recommendations'][:100]}...")
        else:
            print(f"   ⚠ No similar issues found")


def main():
    parser = argparse.ArgumentParser(
        description="Ingest CRO audits into vector database"
    )
    parser.add_argument("--folder-id", help="Google Drive folder ID to download from")
    parser.add_argument("--local-dir", help="Local directory containing DOCX files")
    parser.add_argument(
        "--test-queries", action="store_true", help="Run test queries after ingestion"
    )
    args = parser.parse_args()

    if not args.folder_id and not args.local_dir:
        print("Error: Must specify either --folder-id or --local-dir")
        parser.print_help()
        sys.exit(1)

    # Perform ingestion
    if args.folder_id:
        count = ingest_from_google_drive(args.folder_id)
    else:
        count = ingest_from_local_dir(args.local_dir)

    # Run test queries if requested
    if args.test_queries and count > 0:
        db = VectorDBClient()
        test_queries(db)

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
