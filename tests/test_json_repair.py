"""
Test script for JSON repair functionality
"""
import json
from utils.parsing.json import repair_and_parse_json

# Test cases for JSON repair function
test_cases = [
    {
        "name": "Valid JSON",
        "input": '{"Key point 1": {"Issue": "Test issue", "Recommendation": "Test rec"}}',
        "should_pass": True
    },
    {
        "name": "Trailing comma",
        "input": '{"Key point 1": {"Issue": "Test issue", "Recommendation": "Test rec",}}',
        "should_pass": True
    },
    {
        "name": "Single-line comment",
        "input": '''{"Key point 1": {"Issue": "Test issue", // This is a comment
"Recommendation": "Test rec"}}''',
        "should_pass": True
    },
    {
        "name": "Multi-line comment",
        "input": '{"Key point 1": {"Issue": "Test issue", /* comment */ "Recommendation": "Test rec"}}',
        "should_pass": True
    },
    {
        "name": "Markdown code block",
        "input": '```json\n{"Key point 1": {"Issue": "Test", "Recommendation": "Test"}}\n```',
        "should_pass": True
    },
    {
        "name": "Mixed issues (trailing comma + comment)",
        "input": '''{"Key point 1": {"Issue": "Test", "Recommendation": "Test",}, // comment
"Key point 2": {"Issue": "Test2", "Recommendation": "Test2"}}''',
        "should_pass": True
    }
]

def run_tests():
    passed = 0
    failed = 0

    print("=" * 60)
    print("JSON Repair Function Test Suite")
    print("=" * 60)

    for test in test_cases:
        print(f"\nTest: {test['name']}")
        print(f"Input: {test['input'][:100]}...")

        try:
            result = repair_and_parse_json(test['input'])
            if test['should_pass']:
                print(f"✅ PASSED - Successfully parsed: {list(result.keys())[:3]}")
                passed += 1
            else:
                print(f"❌ FAILED - Should have failed but passed")
                failed += 1
        except Exception as e:
            if not test['should_pass']:
                print(f"✅ PASSED - Correctly failed: {str(e)[:50]}")
                passed += 1
            else:
                print(f"❌ FAILED - {str(e)[:100]}")
                failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
