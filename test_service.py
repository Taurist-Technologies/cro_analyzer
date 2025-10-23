"""
Test script for CRO Analyzer service
Run this after starting the service to test it
"""

import requests
import json
import base64
from pathlib import Path

# Configuration
BASE_URL = "http://localhost:8000"
TEST_URL = "https://www.taurist.com"  # Change to any website you want to test


def test_health_check():
    """Test the health check endpoint"""
    print("🔍 Testing health check...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")
    return response.status_code == 200


def test_analyze_website():
    """Test the analyze endpoint"""
    print(f"🔍 Analyzing website: {TEST_URL}")
    print("This may take 10-20 seconds...\n")

    response = requests.post(
        f"{BASE_URL}/analyze", json={"url": TEST_URL, "deep_info": True}
    )

    if response.status_code != 200:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return False

    data = response.json()

    print(f"✅ Analysis complete!")
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
            screenshot_path = Path(f"issue_{i}_screenshot.png")
            screenshot_data = base64.b64decode(issue["screenshot_base64"])
            screenshot_path.write_bytes(screenshot_data)
            print(f"📸 Screenshot saved to: {screenshot_path.absolute()}\n")

    print("=" * 60)

    # Save full response to JSON
    output_file = Path("analysis_result.json")
    with open(output_file, "w") as f:
        # Remove base64 data for readability
        clean_data = data.copy()
        clean_data["issues"] = [
            {k: v for k, v in issue.items() if k != "screenshot_base64"}
            for issue in data["issues"]
        ]
        json.dump(clean_data, f, indent=2)

    print(f"📄 Full results saved to: {output_file.absolute()}")

    return True


if __name__ == "__main__":
    print("🚀 CRO Analyzer Test Suite\n")

    # Test 1: Health check
    if not test_health_check():
        print("❌ Health check failed. Is the service running?")
        exit(1)

    print("✅ Health check passed!\n")

    # Test 2: Analyze website
    try:
        if test_analyze_website():
            print("\n✅ All tests passed!")
        else:
            print("\n❌ Analysis test failed")
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Could not connect to {BASE_URL}")
        print("Make sure the service is running with: python main.py")
    except Exception as e:
        print(f"\n❌ Error: {e}")
