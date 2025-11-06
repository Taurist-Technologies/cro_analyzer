#!/usr/bin/env python3
"""
Quick test script for cache deletion endpoints
Run this after starting the API server with the new endpoints
"""

import requests
import sys

BASE_URL = "http://localhost:8000"

def test_endpoints():
    print("🧪 Testing Cache Deletion Endpoints\n")

    # Test 1: Health check
    print("1️⃣ Testing health check...")
    response = requests.get(f"{BASE_URL}/health")
    if response.status_code == 200:
        print("   ✅ API is healthy\n")
    else:
        print("   ❌ API is not responding")
        sys.exit(1)

    # Test 2: Clear task cache (should work even if task doesn't exist)
    print("2️⃣ Testing DELETE /cache/task/{task_id}...")
    test_task_id = "test-task-id-12345"
    response = requests.delete(f"{BASE_URL}/cache/task/{test_task_id}")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    if response.status_code == 200:
        print("   ✅ Task cache endpoint works\n")
    else:
        print("   ❌ Task cache endpoint failed\n")

    # Test 3: Clear analysis cache
    print("3️⃣ Testing DELETE /cache/analysis/{url}...")
    test_url = "https://example.com"
    response = requests.delete(f"{BASE_URL}/cache/analysis/{test_url}")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    if response.status_code == 200:
        print("   ✅ Analysis cache endpoint works\n")
    else:
        print("   ❌ Analysis cache endpoint failed\n")

    print("=" * 50)
    print("✅ All endpoint tests completed!")
    print("\n📝 Usage examples:")
    print(f"   curl -X DELETE {BASE_URL}/cache/task/your-task-id")
    print(f"   curl -X DELETE {BASE_URL}/cache/analysis/https://example.com")

if __name__ == "__main__":
    try:
        test_endpoints()
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to API server.")
        print("   Make sure the server is running on http://localhost:8000")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        sys.exit(1)
