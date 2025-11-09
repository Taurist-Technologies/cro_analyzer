import json
import re
import json5
import demjson3
from pathlib import Path
from datetime import datetime


# JSON Repair and Parsing Function
def repair_and_parse_json(response_text: str, deep_info: bool = False) -> dict:
    """
    Multi-layered JSON parsing with auto-repair capabilities.

    Attempts to parse JSON through multiple strategies:
    1. Standard json.loads()
    2. Clean common issues (trailing commas, comments)
    3. json5 parser (tolerates comments and trailing commas)
    4. demjson3 parser (auto-repairs many errors)
    5. Regex extraction fallback for critical fields

    Args:
        response_text: Raw text response from Claude
        deep_info: Whether this is a deep analysis (affects error handling)

    Returns:
        Parsed dictionary from JSON

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

    # Layer 5: Regex extraction fallback with graceful degradation
    try:
        print("⚠️  WARNING: All JSON parsers failed. Attempting regex extraction...")
        print(f"📋 All parser errors: {'; '.join(errors)}")

        if deep_info:
            # Extract deep info structure
            extracted = {
                "total_issues_identified": 0,
                "top_5_issues": [],
                "executive_summary": {
                    "overview": "Analysis unavailable",
                    "how_to_act": "",
                },
                "cro_analysis_score": {
                    "score": 0,
                    "calculation": "",
                    "rating": "Unknown",
                },
                "site_performance_score": {
                    "score": 0,
                    "calculation": "",
                    "rating": "Unknown",
                },
                "conversion_rate_increase_potential": {
                    "percentage": "Unknown",
                    "confidence": "Low",
                    "rationale": "",
                },
            }
        else:
            # Extract standard format (Key point 1, 2, 3)
            extracted = {}

            # Try to find key points using flexible regex (case-insensitive)
            # Match: "Key point N", "key point N", "Keypoint N", "Issue N", "Finding N", "Point N"
            key_point_patterns = [
                r'"([Kk]ey\s*[Pp]oint\s*\d+)":\s*\{[^}]*"([Ii]ssue|[Dd]escription)":\s*"([^"]+)"[^}]*"([Rr]ecommendation|[Ss]olution)":\s*"([^"]+)"',
                r'"([Ii]ssue\s*\d+)":\s*\{[^}]*"([Ii]ssue|[Dd]escription)":\s*"([^"]+)"[^}]*"([Rr]ecommendation|[Ss]olution)":\s*"([^"]+)"',
                r'"([Ff]inding\s*\d+)":\s*\{[^}]*"([Ii]ssue|[Dd]escription)":\s*"([^"]+)"[^}]*"([Rr]ecommendation|[Ss]olution)":\s*"([^"]+)"',
                r'"([Pp]oint\s*\d+)":\s*\{[^}]*"([Ii]ssue|[Dd]escription)":\s*"([^"]+)"[^}]*"([Rr]ecommendation|[Ss]olution)":\s*"([^"]+)"',
            ]

            for pattern in key_point_patterns:
                matches = re.findall(pattern, response_text, re.DOTALL | re.IGNORECASE)
                if matches:
                    for match in matches[:3]:
                        key_name = match[0]
                        # match[1] is the field name (Issue/Description)
                        issue_text = match[2]
                        # match[3] is the field name (Recommendation/Solution)
                        recommendation_text = match[4]
                        extracted[key_name] = {
                            "Issue": issue_text,
                            "Recommendation": recommendation_text,
                        }
                    if extracted:
                        break  # Found matches with this pattern

        # Graceful degradation: Return partial data if we got anything useful
        if extracted:
            if deep_info:
                # Check if we have at least some structure
                if extracted.get("top_5_issues") or extracted.get("executive_summary"):
                    print(f"WARNING: Partial deep info extraction successful via regex")
                    return extracted
            else:
                # Check if we have at least one key point
                if any(key.startswith("Key point") for key in extracted.keys()):
                    print(
                        f"WARNING: Partial extraction successful. Found {len(extracted)} key points via regex"
                    )
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
        f.write(f"Deep Info Mode: {deep_info}\n\n")
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
