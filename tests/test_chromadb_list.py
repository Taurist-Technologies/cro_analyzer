"""Test ChromaDB connection and list existing collections."""

import chromadb
import os
from dotenv import load_dotenv

load_dotenv()

print('Testing Railway ChromaDB Connection...')
print(f'Host: {os.getenv("CHROMA_HOST")}')
print(f'Port: {os.getenv("CHROMA_PORT")}')
print(f'SSL: {os.getenv("CHROMA_SSL")}')
print()

try:
    client = chromadb.HttpClient(
        host=os.getenv('CHROMA_HOST'),
        port=int(os.getenv('CHROMA_PORT', '443')),
        ssl=os.getenv('CHROMA_SSL', 'true').lower() == 'true',
        headers={'Authorization': f"Bearer {os.getenv('CHROMA_AUTH_TOKEN')}"}
    )

    print('✓ Connection successful')
    print()

    # Try to list collections WITHOUT creating
    print('Attempting to list existing collections...')
    collections = client.list_collections()

    print(f'✓ Found {len(collections)} collection(s):')
    print('=' * 60)

    if collections:
        for col in collections:
            print(f'  Name: {col.name}')
            print(f'  Count: {col.count():,} documents')
            print(f'  Metadata: {col.metadata}')
            print()
    else:
        print('  (No collections found - database is empty)')
        print()
        print('This may indicate the ChromaDB server needs collection migration.')

except Exception as e:
    print(f'✗ Error: {e}')
    import traceback
    traceback.print_exc()
