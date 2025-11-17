"""
Test script for CRO Analyzer service
Run this after starting the service to test it

Tests both sync and async API patterns:
- Sync: POST /analyze (blocking, returns result immediately)
- Async: POST /analyze/async (non-blocking, poll for status)
"""

import requests
import json
import base64
import time
from pathlib import Path

# Configuration
BASE_URL = "http://localhost:8000"
TEST_URL = "https://mifold.com"  # Change to any website you want to test


def test_health_check():
    """Test the basic health check endpoint"""
    print("🔍 Testing health check...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")
    return response.status_code == 200


def test_detailed_status():
    """Test the detailed status endpoint"""
    print("🔍 Testing detailed status endpoint...")
    response = requests.get(f"{BASE_URL}/status/detailed")
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"Overall Status: {data.get('overall_status', 'unknown')}")

        # Display component statuses
        print(f"  API: {data.get('api', 'unknown')}")
        print(f"  Redis: {data.get('redis', 'unknown')}")
        print(f"  Celery: {data.get('celery', 'unknown')}")
        print(f"  Browser Pool: {data.get('browser_pool', 'unknown')}")
        print(f"  Anthropic API: {data.get('anthropic_api', 'unknown')}")

        # Display worker info if available
        if "celery_workers" in data and data["celery_workers"]:
            print(f"  Active Workers: {len(data['celery_workers'])}")
            for worker in data["celery_workers"]:
                print(f"    - {worker}")

        # Display Redis stats if available
        if "redis_stats" in data:
            stats = data["redis_stats"]
            print(f"\n  Redis Stats:")
            print(f"    Connected Clients: {stats.get('connected_clients', 'N/A')}")
            print(f"    Memory Used: {stats.get('used_memory_human', 'N/A')}")
            print(
                f"    Commands Processed: {stats.get('total_commands_processed', 'N/A')}"
            )
        print()
    else:
        print(f"Response: {response.text}\n")

    return response.status_code == 200


def test_analyze_website_sync():
    """Test the synchronous analyze endpoint (blocking)"""
    print(f"🔍 Testing SYNC analysis: {TEST_URL}")
    print("This may take 10-20 seconds (blocking)...\n")

    response = requests.post(
        f"{BASE_URL}/analyze", json={"url": TEST_URL, "include_screenshots": False}
    )

    if response.status_code != 200:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return False

    data = response.json()
    _display_analysis_results(data, "sync")
    return True


def test_analyze_website_async():
    """Test the asynchronous analyze endpoint (non-blocking with polling)"""
    print(f"🔍 Testing ASYNC analysis: {TEST_URL}")
    print("Submitting task...\n")

    # Step 1: Submit analysis task
    response = requests.post(
        f"{BASE_URL}/analyze/async", json={"url": TEST_URL, "include_screenshots": False}
    )

    if response.status_code != 200:
        print(f"❌ Error submitting task: {response.status_code}")
        print(response.text)
        return False

    task_data = response.json()
    task_id = task_data["task_id"]
    print(f"✅ Task submitted: {task_id}")
    print(f"Poll URL: {task_data['poll_url']}\n")

    # Step 2: Poll for task completion
    print("⏳ Polling for task completion...")
    max_polls = 60  # Max 60 polls (60 seconds with 1s delay)
    poll_count = 0

    while poll_count < max_polls:
        poll_count += 1
        time.sleep(1)  # Wait 1 second between polls

        status_response = requests.get(f"{BASE_URL}/analyze/status/{task_id}")
        if status_response.status_code != 200:
            print(f"❌ Error polling status: {status_response.status_code}")
            return False

        status_data = status_response.json()
        current_status = status_data["status"]

        print(f"  Poll #{poll_count}: {current_status}", end="\r")

        if current_status == "SUCCESS":
            print(f"\n✅ Task completed after {poll_count} seconds!")
            result = status_data.get("result")
            if result:
                _display_analysis_results(result, "async")
                return True
            else:
                print("⚠️  Task succeeded but no result found")
                return False

        elif current_status == "FAILURE":
            print(f"\n❌ Task failed: {status_data.get('error', 'Unknown error')}")
            return False

        elif current_status in ["PENDING", "STARTED"]:
            continue  # Keep polling

    print(f"\n⏰ Timeout: Task did not complete within {max_polls} seconds")
    return False


def _display_analysis_results(data: dict, mode: str):
    """Helper function to display analysis results"""
    print(f"\n{'='*60}")
    print(f"ANALYSIS RESULTS ({mode.upper()} MODE)")
    print(f"{'='*60}")
    print(f"URL: {data['url']}")
    print(f"Analyzed at: {data['analyzed_at']}")
    print(f"Issues found: {len(data['issues'])}\n")

    # Display issues
    for i, issue in enumerate(data["issues"], 1):
        print(f"{'='*60}")
        print(f"Issue #{i}: {issue['title']}")
        print(f"{'='*60}")
        print(f"\n📋 Description:")
        print(f"   {issue['description']}\n")
        print(f"💡 Recommendation:")
        print(f"   {issue['recommendation']}\n")

        # Save screenshot if present
        if issue.get("screenshot_base64"):
            screenshot_path = Path(f"{mode}_issue_{i}_screenshot.png")
            screenshot_data = base64.b64decode(issue["screenshot_base64"])
            screenshot_path.write_bytes(screenshot_data)
            print(f"📸 Screenshot saved to: {screenshot_path.absolute()}\n")

    print("=" * 60)

    # Save full response to JSON
    output_file = Path(f"analysis_result_{mode}.json")
    with open(output_file, "w") as f:
        # Remove base64 data for readability
        clean_data = data.copy()
        clean_data["issues"] = [
            {k: v for k, v in issue.items() if k != "screenshot_base64"}
            for issue in data["issues"]
        ]
        json.dump(clean_data, f, indent=2)

    print(f"📄 Full results saved to: {output_file.absolute()}\n")


if __name__ == "__main__":
    print("🚀 CRO Analyzer Test Suite\n")
    print("=" * 60)

    test_mode = input(
        "Select test mode:\n1. Quick (health checks only)\n2. Sync (blocking analysis)\n3. Async (non-blocking analysis)\n4. Full (all tests)\n\nEnter choice (1-4): "
    ).strip()
    print("=" * 60 + "\n")

    # Test 2: Status check
    if not test_detailed_status():
        print("❌ Status check failed")
        exit(1)

    print("✅ Status check passed!\n")

    # Test 3: Analyze website
    try:
        # Test 1: Basic health check
        print("TEST 1: Basic Health Check")
        print("-" * 60)
        if not test_health_check():
            print("❌ Health check failed. Is the service running?")
            exit(1)
        print("✅ Basic health check passed!\n")

        # Test 2: Detailed status check
        print("TEST 2: Detailed Status Check")
        print("-" * 60)
        if not test_detailed_status():
            print("⚠️  Detailed status check failed (may need Redis/Celery)")
        else:
            print("✅ Detailed status check passed!\n")

        if test_mode == "1":
            print("\n✅ Quick tests completed!")
            exit(0)

        # Test 3: Sync analysis
        if test_mode in ["2", "4"]:
            print("TEST 3: Synchronous Analysis")
            print("-" * 60)
            if test_analyze_website_sync():
                print("✅ Sync analysis test passed!\n")
            else:
                print("❌ Sync analysis test failed\n")

        # Test 4: Async analysis
        if test_mode in ["3", "4"]:
            print("TEST 4: Asynchronous Analysis")
            print("-" * 60)
            if test_analyze_website_async():
                print("✅ Async analysis test passed!\n")
            else:
                print("❌ Async analysis test failed\n")

        print("\n" + "=" * 60)
        print("✅ All selected tests completed!")
        print("=" * 60)

    except requests.exceptions.ConnectionError:
        print(f"\n❌ Could not connect to {BASE_URL}")
        print("Make sure the service is running:")
        print("  - For sync mode: python3 main.py")
        print("  - For async mode: docker-compose up")
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
