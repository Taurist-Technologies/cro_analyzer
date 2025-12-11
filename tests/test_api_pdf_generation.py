#!/usr/bin/env python3
"""
Test PDF generation with data from API endpoint
Uses groot.com analysis data from task ID: ac95ecdc-111a-4d9e-a074-6c005b9ae51a
"""

import json
import requests
from utils.reporting.pdf import register_fonts, generate_pdf

# Fetch analysis result from API
task_id = "ac95ecdc-111a-4d9e-a074-6c005b9ae51a"
api_url = f"http://localhost:8000/analyze/result/{task_id}"

print(f"Fetching analysis data from API: {api_url}")
response = requests.get(api_url)

if response.status_code != 200:
    print(f"❌ Failed to fetch data: HTTP {response.status_code}")
    print(f"Response: {response.text}")
    exit(1)

response_data = response.json()

# API returns wrapper with task_id, status, and result
# The actual audit data is in the 'result' key
if 'result' not in response_data:
    print(f"❌ No 'result' key in API response")
    print(f"Response keys: {list(response_data.keys())}")
    exit(1)

audit_data = response_data['result']
print(f"✅ Successfully fetched analysis data for: {audit_data['url']}")

# Register fonts
register_fonts()

# Generate PDF
output_path = "/Users/rhillx/Code/Taurist/cro_analyzer/Groot_CRO_Audit_API_Test.pdf"

try:
    generate_pdf(audit_data, output_path)
    print(f"✅ PDF generated successfully: {output_path}")
    print(f"\nPDF Details:")
    print(f"   - URL: {audit_data['url']}")
    print(f"   - Analyzed: {audit_data['analyzed_at']}")
    print(f"   - Total issues identified: {audit_data['total_issues_identified']}")
    print(f"   - Issues shown: {len(audit_data['issues'])}")
    print(f"   - Potential Uplift: {audit_data['conversion_rate_increase_potential']['percentage']} ({audit_data['conversion_rate_increase_potential']['confidence']} confidence)")
    print(f"\nScorecards:")
    for key, scorecard in audit_data['scorecards'].items():
        print(f"   - {key}: {scorecard['score']}/100 ({scorecard['color']})")
except Exception as e:
    print(f"❌ PDF generation failed with error:")
    print(f"   Error type: {type(e).__name__}")
    print(f"   Error message: {str(e)}")
    import traceback
    print(f"\nFull traceback:")
    traceback.print_exc()
