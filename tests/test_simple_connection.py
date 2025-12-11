#!/usr/bin/env python3
"""Simple Railway ChromaDB connection test"""

import chromadb
import os
from dotenv import load_dotenv

load_dotenv()

print("Testing connection to Railway ChromaDB...")
print(f"Host: {os.getenv('CHROMA_HOST')}")
print(f"Port: 443")
print(f"SSL: True")
print(f"Auth: {'Set' if os.getenv('CHROMA_AUTH_TOKEN') else 'Not set'}")

# Test 1: Default tenant (no tenant specified)
print("\n=== Test 1: Default tenant ===")
try:
    client = chromadb.HttpClient(
        host=os.getenv('CHROMA_HOST'),
        port=443,
        ssl=True,
        headers={'Authorization': f'Bearer {os.getenv("CHROMA_AUTH_TOKEN")}'}
    )
    print(f"✓ Heartbeat: {client.heartbeat()}")
    collections = client.list_collections()
    print(f"✓ Collections: {len(collections)} found")
    for col in collections:
        print(f"  - {col.name}")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 2: With specific tenant
print("\n=== Test 2: Specific tenant ===")
try:
    client = chromadb.HttpClient(
        host=os.getenv('CHROMA_HOST'),
        port=443,
        ssl=True,
        headers={'Authorization': f'Bearer {os.getenv("CHROMA_AUTH_TOKEN")}'},
        tenant=os.getenv('CHROMA_TENANT'),
        database=os.getenv('CHROMA_DATABASE')
    )
    print(f"✓ Heartbeat: {client.heartbeat()}")
    collections = client.list_collections()
    print(f"✓ Collections: {len(collections)} found")
    for col in collections:
        print(f"  - {col.name}")
except Exception as e:
    print(f"✗ Error: {e}")

print("\nDone!")
