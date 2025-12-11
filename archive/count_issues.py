#!/usr/bin/env python3
"""
Quick script to count total issues in ChromaDB collections.

Usage:
    python3 count_issues.py
"""

import chromadb
import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 70)
print("📊 CHROMADB ISSUE COUNTER")
print("=" * 70)

print(f"\n🔌 Connecting to ChromaDB...")
print(f"   Host: {os.getenv('CHROMA_HOST')}:{os.getenv('CHROMA_PORT')}")

try:
    # Create client
    client = chromadb.HttpClient(
        host=os.getenv('CHROMA_HOST'),
        port=int(os.getenv('CHROMA_PORT', 443)),
        ssl=os.getenv('CHROMA_SSL', 'true').lower() == 'true',
        headers={'Authorization': f"Bearer {os.getenv('CHROMA_AUTH_TOKEN')}"}
    )

    print("   ✓ Connected successfully\n")

    # List all collections
    collections = client.list_collections()

    if not collections:
        print("⚠️  No collections found in ChromaDB")
        exit(0)

    print(f"📋 Found {len(collections)} collection(s):\n")
    print("=" * 70)

    total_issues = 0

    for col in collections:
        count = col.count()
        total_issues += count
        print(f"  {col.name:<40} {count:>10,} issues")

    print("=" * 70)
    print(f"\n✨ TOTAL ISSUES ACROSS ALL COLLECTIONS: {total_issues:,}")

    # Show detailed breakdown for CRO audit collections
    cro_collections = [c for c in collections if 'cro' in c.name.lower() or 'audit' in c.name.lower() or 'issue' in c.name.lower()]

    if cro_collections:
        print(f"\n🔍 CRO Audit Collection Details:")
        print("=" * 70)

        for col in cro_collections:
            print(f"\n  Collection: {col.name}")
            print(f"  Total Issues: {col.count():,}")

            # Get sample to show client breakdown
            try:
                sample = col.peek(limit=100)  # Sample more for better client list
                if sample['metadatas']:
                    clients = {}
                    for m in sample['metadatas']:
                        client_name = m.get('client_name', 'Unknown')
                        clients[client_name] = clients.get(client_name, 0) + 1

                    print(f"  Sample Clients ({len(clients)} unique in first 100 docs):")
                    for client_name in sorted(clients.keys()):
                        print(f"    - {client_name}: {clients[client_name]} issues")
            except Exception as e:
                print(f"  (Could not retrieve sample: {e})")

    print("\n" + "=" * 70)
    print("✅ Count complete!")
    print("=" * 70 + "\n")

except Exception as e:
    print(f"\n❌ Error: {e}")
    print("\n💡 Troubleshooting:")
    print("   1. Check that Railway ChromaDB service is running")
    print("   2. Verify CHROMA_HOST and CHROMA_PORT in .env")
    print("   3. Confirm CHROMA_AUTH_TOKEN is correct")
    print("   4. Test connection: curl https://<host>/api/v1/heartbeat")

    import traceback
    traceback.print_exc()
    exit(1)
