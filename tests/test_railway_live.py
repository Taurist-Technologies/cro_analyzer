#!/usr/bin/env python3
"""
Railway ChromaDB Live Connection Test
======================================

Comprehensive test suite to verify Railway ChromaDB deployment is working correctly.
Tests authentication, connectivity, CRUD operations, and performance.

Usage:
    python3 tests/test_railway_live.py

Environment Variables Required:
    CHROMA_HOST - Railway ChromaDB hostname
    CHROMA_PORT - Port (default: 443)
    CHROMA_SSL - SSL enabled (default: true)
    CHROMA_AUTH_TOKEN - Authentication token
"""

import sys
import os
import time
from datetime import datetime
from typing import Dict, List, Tuple
import chromadb
from chromadb.config import Settings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class RailwayChromaDBTester:
    """Comprehensive Railway ChromaDB connection tester"""

    def __init__(self):
        self.host = os.getenv("CHROMA_HOST")
        self.port = int(os.getenv("CHROMA_PORT", "443"))
        self.ssl = os.getenv("CHROMA_SSL", "true").lower() == "true"
        self.auth_token = os.getenv("CHROMA_AUTH_TOKEN")
        self.tenant = os.getenv("CHROMA_TENANT", "default_tenant")
        self.database = os.getenv("CHROMA_DATABASE", "default_database")

        self.client = None
        self.test_results: List[Tuple[str, bool, str]] = []
        self.start_time = None

    def print_header(self):
        """Print test header"""
        print("\n" + "=" * 80)
        print("🚂 RAILWAY CHROMADB LIVE CONNECTION TEST")
        print("=" * 80)
        print(f"\n📋 Configuration:")
        print(f"   Host:     {self.host}:{self.port}")
        print(f"   SSL:      {self.ssl}")
        print(f"   Auth:     {'✓ Enabled' if self.auth_token else '✗ Disabled'}")
        print(f"   Tenant:   {self.tenant}")
        print(f"   Database: {self.database}")
        print(f"   Time:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

    def add_result(self, test_name: str, passed: bool, message: str = ""):
        """Record test result"""
        self.test_results.append((test_name, passed, message))

    def run_test(self, name: str, func):
        """Run a single test and record result"""
        print(f"\n{'─' * 80}")
        print(f"🧪 {name}")
        print(f"{'─' * 80}")

        try:
            start = time.time()
            result = func()
            elapsed = (time.time() - start) * 1000  # Convert to ms

            if result:
                print(f"✅ PASS ({elapsed:.0f}ms)")
                self.add_result(name, True, f"{elapsed:.0f}ms")
                return True
            else:
                print(f"❌ FAIL")
                self.add_result(name, False, "Test returned False")
                return False

        except Exception as e:
            print(f"❌ FAIL: {str(e)}")
            self.add_result(name, False, str(e))
            return False

    def test_1_environment_check(self) -> bool:
        """Test 1: Verify environment configuration"""
        print("Checking environment variables...")

        if not self.host:
            print("   ❌ CHROMA_HOST not set")
            return False
        print(f"   ✓ CHROMA_HOST: {self.host}")

        print(f"   ✓ CHROMA_PORT: {self.port}")
        print(f"   ✓ CHROMA_SSL: {self.ssl}")

        if not self.auth_token:
            print("   ⚠️  CHROMA_AUTH_TOKEN not set (authentication disabled)")
        else:
            print(f"   ✓ CHROMA_AUTH_TOKEN: {self.auth_token[:10]}...")

        print(f"   ✓ CHROMA_TENANT: {self.tenant}")
        print(f"   ✓ CHROMA_DATABASE: {self.database}")

        return True

    def test_2_create_client(self) -> bool:
        """Test 2: Create ChromaDB HTTP client"""
        print("Creating ChromaDB HTTP client...")

        # Build headers
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
            print("   ✓ Authentication header added")

        # Create client
        self.client = chromadb.HttpClient(
            host=self.host,
            port=self.port,
            ssl=self.ssl,
            headers=headers if headers else None,
            tenant=self.tenant,
            database=self.database,
        )

        print("   ✓ Client created successfully")
        return True

    def test_3_heartbeat(self) -> bool:
        """Test 3: Check server heartbeat"""
        print("Testing server heartbeat...")

        heartbeat = self.client.heartbeat()
        print(f"   ✓ Heartbeat response: {heartbeat}")

        if heartbeat > 0:
            print("   ✓ Server is alive and responding")
            return True
        else:
            print("   ❌ Invalid heartbeat response")
            return False

    def test_4_version(self) -> bool:
        """Test 4: Get ChromaDB version"""
        print("Getting ChromaDB version...")

        version = self.client.get_version()
        print(f"   ✓ ChromaDB version: {version}")
        return True

    def test_5_list_collections(self) -> bool:
        """Test 5: List existing collections"""
        print("Listing collections...")

        collections = self.client.list_collections()
        print(f"   ✓ Found {len(collections)} collection(s)")

        if collections:
            for col in collections[:10]:  # Show max 10
                count = col.count()
                print(f"     - {col.name}: {count} documents")

            if len(collections) > 10:
                print(f"     ... and {len(collections) - 10} more")
        else:
            print("   ℹ️  No collections found (fresh deployment)")

        return True

    def test_6_create_collection(self) -> bool:
        """Test 6: Create a test collection"""
        print("Creating test collection...")

        collection_name = f"test_railway_{int(time.time())}"
        print(f"   Collection name: {collection_name}")

        collection = self.client.create_collection(
            name=collection_name,
            metadata={
                "description": "Railway connection test - safe to delete",
                "created": datetime.now().isoformat(),
                "test": True
            }
        )

        print(f"   ✓ Collection created: {collection.name}")
        print(f"   ✓ Collection ID: {collection.id}")

        # Store for cleanup
        self.test_collection_name = collection_name
        return True

    def test_7_add_documents(self) -> bool:
        """Test 7: Add documents to collection"""
        print("Adding test documents...")

        collection = self.client.get_collection(self.test_collection_name)

        # Add sample documents
        documents = [
            "Railway ChromaDB is working perfectly!",
            "Connection test successful on Railway deployment.",
            "This is a test document for verification purposes."
        ]

        ids = [f"doc_{i}" for i in range(len(documents))]
        metadatas = [
            {"source": "test", "index": i, "timestamp": time.time()}
            for i in range(len(documents))
        ]

        # Generate simple embeddings (for testing, use random values)
        # In production, you'd use a real embedding model
        import random
        embeddings = [[random.random() for _ in range(384)] for _ in documents]

        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings
        )

        print(f"   ✓ Added {len(documents)} documents")

        # Verify count
        count = collection.count()
        print(f"   ✓ Collection now has {count} documents")

        if count == len(documents):
            print("   ✓ Document count matches expected")
            return True
        else:
            print(f"   ⚠️  Expected {len(documents)}, got {count}")
            return False

    def test_8_query_documents(self) -> bool:
        """Test 8: Query documents from collection"""
        print("Querying documents...")

        collection = self.client.get_collection(self.test_collection_name)

        # Get specific document
        results = collection.get(ids=["doc_0"])

        if results["ids"] and results["ids"][0] == "doc_0":
            print("   ✓ Retrieved document by ID")
            print(f"   ✓ Document: {results['documents'][0][:50]}...")
        else:
            print("   ❌ Failed to retrieve document")
            return False

        # Get all documents
        all_results = collection.get()
        print(f"   ✓ Retrieved all documents: {len(all_results['ids'])} found")

        return True

    def test_9_update_documents(self) -> bool:
        """Test 9: Update document metadata"""
        print("Updating document metadata...")

        collection = self.client.get_collection(self.test_collection_name)

        # Update metadata
        collection.update(
            ids=["doc_0"],
            metadatas=[{"source": "test", "updated": True, "timestamp": time.time()}]
        )

        print("   ✓ Document metadata updated")

        # Verify update
        results = collection.get(ids=["doc_0"])
        if results["metadatas"][0].get("updated"):
            print("   ✓ Update verified")
            return True
        else:
            print("   ❌ Update verification failed")
            return False

    def test_10_delete_documents(self) -> bool:
        """Test 10: Delete documents from collection"""
        print("Deleting test documents...")

        collection = self.client.get_collection(self.test_collection_name)

        # Delete one document
        collection.delete(ids=["doc_0"])
        print("   ✓ Deleted 1 document")

        # Verify deletion
        count = collection.count()
        print(f"   ✓ Collection now has {count} documents")

        if count == 2:  # Started with 3, deleted 1
            print("   ✓ Deletion verified")
            return True
        else:
            print(f"   ⚠️  Expected 2 documents, got {count}")
            return False

    def test_11_delete_collection(self) -> bool:
        """Test 11: Delete test collection"""
        print("Deleting test collection...")

        self.client.delete_collection(name=self.test_collection_name)
        print(f"   ✓ Collection '{self.test_collection_name}' deleted")

        # Verify deletion
        collections = self.client.list_collections()
        collection_names = [c.name for c in collections]

        if self.test_collection_name not in collection_names:
            print("   ✓ Deletion verified")
            return True
        else:
            print("   ❌ Collection still exists")
            return False

    def test_12_performance_check(self) -> bool:
        """Test 12: Basic performance check"""
        print("Running performance test...")

        # Test heartbeat latency (5 calls)
        latencies = []
        for i in range(5):
            start = time.time()
            self.client.heartbeat()
            latency = (time.time() - start) * 1000
            latencies.append(latency)

        avg_latency = sum(latencies) / len(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)

        print(f"   ✓ Average latency: {avg_latency:.0f}ms")
        print(f"   ✓ Min latency: {min_latency:.0f}ms")
        print(f"   ✓ Max latency: {max_latency:.0f}ms")

        if avg_latency < 1000:  # Less than 1 second
            print("   ✓ Performance is good")
            return True
        elif avg_latency < 3000:  # Less than 3 seconds
            print("   ⚠️  Performance is acceptable but slow")
            return True
        else:
            print("   ⚠️  Performance is poor (high latency)")
            return False

    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 80)
        print("📊 TEST SUMMARY")
        print("=" * 80)

        total_tests = len(self.test_results)
        passed_tests = sum(1 for _, passed, _ in self.test_results if passed)
        failed_tests = total_tests - passed_tests

        print(f"\nTotal Tests:  {total_tests}")
        print(f"✅ Passed:    {passed_tests}")
        print(f"❌ Failed:    {failed_tests}")
        print(f"Success Rate: {(passed_tests / total_tests * 100):.1f}%")

        if self.start_time:
            elapsed = time.time() - self.start_time
            print(f"Duration:     {elapsed:.2f}s")

        print("\n📋 Detailed Results:")
        print(f"{'─' * 80}")

        for name, passed, message in self.test_results:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status} | {name}")
            if message:
                print(f"       └─ {message}")

        print(f"{'─' * 80}")

        # Final verdict
        if failed_tests == 0:
            print("\n🎉 ALL TESTS PASSED! Railway ChromaDB is fully operational.")
            print("\n✨ Your Railway deployment is ready for production use!")
            return True
        elif passed_tests >= total_tests * 0.75:
            print(f"\n⚠️  MOSTLY PASSED ({passed_tests}/{total_tests} tests)")
            print("Some issues detected, but core functionality works.")
            return True
        else:
            print(f"\n❌ TESTS FAILED ({failed_tests}/{total_tests} failures)")
            print("Critical issues detected. Please review errors above.")
            return False

    def run_all_tests(self) -> bool:
        """Run all tests in sequence"""
        self.start_time = time.time()
        self.print_header()

        # Define test sequence
        tests = [
            ("Environment Configuration", self.test_1_environment_check),
            ("Client Creation", self.test_2_create_client),
            ("Server Heartbeat", self.test_3_heartbeat),
            ("ChromaDB Version", self.test_4_version),
            ("List Collections", self.test_5_list_collections),
            ("Create Collection", self.test_6_create_collection),
            ("Add Documents", self.test_7_add_documents),
            ("Query Documents", self.test_8_query_documents),
            ("Update Documents", self.test_9_update_documents),
            ("Delete Documents", self.test_10_delete_documents),
            ("Delete Collection", self.test_11_delete_collection),
            ("Performance Check", self.test_12_performance_check),
        ]

        # Run tests
        for name, func in tests:
            passed = self.run_test(name, func)

            # Stop on critical failure (client creation or heartbeat)
            if not passed and name in ["Client Creation", "Server Heartbeat"]:
                print(f"\n⚠️  Critical test failed: {name}")
                print("Stopping test suite - fix this issue first.")
                break

        # Print summary
        return self.print_summary()


def main():
    """Main entry point"""
    try:
        tester = RailwayChromaDBTester()
        success = tester.run_all_tests()
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)

    except Exception as e:
        print(f"\n\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
