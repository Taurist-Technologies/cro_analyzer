import json
import re
import json5
import demjson3
from pathlib import Path
from datetime import datetime


# JSON Repair and Parsing Function
def repair_and_parse_json(response_text: str) -> dict:
    """
    Multi-layered JSON parsing with auto-repair capabilities.

    Attempts to parse JSON through multiple strategies:
    1. Standard json.loads()
    2. Clean common issues (trailing commas, comments)
    3. json5 parser (tolerates comments and trailing commas)
    4. demjson3 parser (auto-repairs many errors)
    5. Regex extraction fallback for enhanced mode structure

    Args:
        response_text: Raw text response from Claude

    Returns:
        Parsed dictionary with enhanced mode structure (quick_wins + scorecards)

    Raises:
        ValueError: If all parsing attempts fail
    """
    original_text = response_text
    errors = []

    # Layer 1: Try standard JSON parser first
    try:
        print("🔧 Layer 1: Attempting standard json.loads()...")
        result = json.loads(response_text)
        print("✅ Layer 1: Standard JSON parsing succeeded!")
        return result
    except json.JSONDecodeError as e:
        errors.append(f"Standard JSON: {str(e)}")
        print(f"❌ Layer 1 failed: {str(e)}")

    # Layer 2: Clean common Claude JSON mistakes
    try:
        print(
            "🔧 Layer 2: Attempting JSON with cleaning (trailing commas, comments, etc.)..."
        )
        cleaned = response_text

        # Remove trailing commas before closing braces/brackets
        cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)

        # Remove single-line comments (// ...)
        cleaned = re.sub(r"//.*?\n", "\n", cleaned)

        # Remove multi-line comments (/* ... */)
        cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)

        # Fix common quote escaping issues
        cleaned = cleaned.replace('\\"', '"').replace("'", '"')

        # Try parsing cleaned version
        result = json.loads(cleaned)
        print("✅ Layer 2: Cleaned JSON parsing succeeded!")
        return result
    except json.JSONDecodeError as e:
        errors.append(f"Cleaned JSON: {str(e)}")
        print(f"❌ Layer 2 failed: {str(e)}")

    # Layer 3: Try json5 (tolerates trailing commas and comments)
    try:
        print("🔧 Layer 3: Attempting json5 parser...")
        result = json5.loads(response_text)
        print("✅ Layer 3: JSON5 parsing succeeded!")
        return result
    except Exception as e:
        errors.append(f"JSON5: {str(e)}")
        print(f"❌ Layer 3 failed: {str(e)}")

    # Layer 4: Try demjson3 (auto-repairs many JSON errors)
    try:
        print("🔧 Layer 4: Attempting demjson3 parser...")
        result = demjson3.decode(response_text)
        print("✅ Layer 4: DemJSON parsing succeeded!")
        return result
    except Exception as e:
        errors.append(f"DemJSON: {str(e)}")
        print(f"❌ Layer 4 failed: {str(e)}")

    # Layer 5: Regex extraction fallback for enhanced mode structure
    try:
        print("⚠️  WARNING: All JSON parsers failed. Attempting regex extraction...")
        print(f"📋 All parser errors: {'; '.join(errors)}")

        # Extract enhanced mode structure (quick_wins + scorecards)
        extracted = {
            "quick_wins": [],
            "scorecards": {
                "ux_design": {"score": 0, "color": "red", "rationale": "Analysis unavailable"},
                "content_copy": {"score": 0, "color": "red", "rationale": "Analysis unavailable"},
                "site_performance": {"score": 0, "color": "red", "rationale": "Analysis unavailable"},
                "conversion_potential": {"score": 0, "color": "red", "rationale": "Analysis unavailable"},
                "mobile_experience": {"score": 0, "color": "red", "rationale": "Analysis unavailable"},
            },
            "executive_summary": {
                "overview": "Analysis unavailable - JSON parsing failed",
                "how_to_act": "Please retry the analysis",
            },
            "conversion_rate_increase_potential": {
                "percentage": "Unknown",
                "confidence": "Low",
                "rationale": "Analysis incomplete due to parsing failure",
            },
        }

        # Try to extract quick_wins if available in malformed JSON
        quick_win_pattern = r'"quick_wins":\s*\[(.*?)\]'
        quick_wins_match = re.search(quick_win_pattern, response_text, re.DOTALL)
        if quick_wins_match:
            print(f"ℹ️  Found quick_wins array in response")

        # Return graceful degradation structure
        print(f"⚠️  Returning graceful degradation structure (empty quick_wins)")
        return extracted

    except Exception as e:
        errors.append(f"Regex extraction: {str(e)}")

    # All layers failed - save for debugging and raise error
    error_log_path = Path("failed_json_responses")
    error_log_path.mkdir(exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_file = error_log_path / f"failed_{timestamp}.txt"

    with open(log_file, "w") as f:
        f.write(f"=== PARSING FAILURE DEBUG LOG ===\n")
        f.write(f"Timestamp: {timestamp}\n")
        f.write(f"Analysis Mode: Section-based (Enhanced)\n\n")
        f.write(f"=== ORIGINAL RESPONSE ===\n{original_text}\n\n")
        f.write(f"=== CLEANED RESPONSE ===\n{response_text}\n\n")
        f.write(f"=== PARSING ERRORS ===\n")
        for i, error in enumerate(errors, 1):
            f.write(f"{i}. {error}\n")
        f.write(f"\n=== RESPONSE LENGTH ===\n")
        f.write(f"Original: {len(original_text)} chars\n")
        f.write(f"Cleaned: {len(response_text)} chars\n")
        f.write(f"\n=== FIRST 500 CHARS OF RESPONSE ===\n")
        f.write(original_text[:500])

    print(f"❌ JSON parsing failed. Debug log saved to {log_file}")
    print(f"Response preview: {original_text[:200]}...")

    # Return detailed error
    raise ValueError(
        f"Failed to parse JSON after all attempts. "
        f"Errors: {'; '.join(errors[:2])}. "
        f"Debug log saved to {log_file} for troubleshooting."
    )
