"""
CRO Analyzer Service - Architecture Overview
=============================================

┌─────────────────────────────────────────────────────────────────────────┐
│                              n8n WORKFLOW                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌────────────────────────┐    │
│  │   Webhook    │───▶│     HTTP     │───▶│  Process & Send        │    │
│  │   Trigger    │    │   Request    │    │  Results (Email/Slack) │    │
│  └──────────────┘    └──────┬───────┘    └────────────────────────┘    │
└──────────────────────────────┼───────────────────────────────────────────┘
                                │
                                │ POST /analyze
                                │ {"url": "https://example.com"}
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       FASTAPI BACKEND SERVICE                             │
│                           (main.py)                                       │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  1. Receive URL Request                                          │   │
│  │     ↓                                                             │   │
│  │  2. Launch Playwright Browser                                    │   │
│  │     ↓                                                             │   │
│  │  3. Navigate to Website & Wait for Load                          │   │
│  │     ↓                                                             │   │
│  │  4. Capture Full-Page Screenshot                                 │   │
│  │     ↓                                                             │   │
│  │  5. Send Screenshot + Prompt to Claude API                       │   │
│  │     ↓                                                             │   │
│  │  6. Parse Claude's JSON Response                                 │   │
│  │     ↓                                                             │   │
│  │  7. Format Response with Issues + Screenshots                    │   │
│  │     ↓                                                             │   │
│  │  8. Return JSON Response                                         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└──────────────────────────┬────────────────────────────┬─────────────────┘
                           │                            │
                           │                            │
                    ┌──────▼──────┐             ┌──────▼──────┐
                    │  Playwright  │             │   Claude    │
                    │   Browser    │             │     API     │
                    │             │             │  (Anthropic) │
                    │  - Chromium │             │             │
                    │  - Screenshot│             │  - Vision   │
                    │  - Headless │             │  - Analysis │
                    └─────────────┘             └─────────────┘


DATA FLOW EXAMPLE:
==================

INPUT (from n8n):
-----------------
{
  "url": "https://example.com"
}

                    ↓

PLAYWRIGHT PROCESS:
-------------------
1. Launch browser (Chromium, headless)
2. Navigate to https://example.com
3. Wait for network idle
4. Capture full-page screenshot
5. Convert to base64

                    ↓

CLAUDE API REQUEST:
-------------------
{
  "model": "claude-sonnet-4-20250514",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "image", "source": {"type": "base64", "data": "..."}},
      {"type": "text", "text": "Analyze this website for CRO issues..."}
    ]
  }]
}

                    ↓

CLAUDE RESPONSE:
----------------
{
  "issues": [
    {
      "title": "Weak Call-to-Action",
      "description": "The primary CTA button lacks contrast...",
      "recommendation": "Use a high-contrast color like..."
    },
    {
      "title": "Missing Trust Signals",
      "description": "No social proof visible above the fold...",
      "recommendation": "Add customer testimonials or logos..."
    }
  ]
}

                    ↓

OUTPUT (to n8n):
----------------
{
  "url": "https://example.com",
  "analyzed_at": "2025-10-17T10:30:00.000000",
  "issues": [
    {
      "title": "Weak Call-to-Action",
      "description": "The primary CTA button lacks contrast...",
      "recommendation": "Use a high-contrast color like...",
      "screenshot_base64": "iVBORw0KGgoAAAANS..."
    },
    {
      "title": "Missing Trust Signals",
      "description": "No social proof visible above the fold...",
      "recommendation": "Add customer testimonials or logos...",
      "screenshot_base64": "iVBORw0KGgoAAAANS..."
    }
  ]
}


DEPLOYMENT OPTIONS:
===================

Local Development:
  python main.py
  → http://localhost:8000

Docker Container:
  docker build -t cro-analyzer .
  docker run -p 8000:8000 -e ANTHROPIC_API_KEY=xxx cro-analyzer
  → http://localhost:8000

Cloud Deployment (e.g., DigitalOcean, AWS EC2):
  1. Deploy container or install Python environment
  2. Set environment variables
  3. Use reverse proxy (nginx) for HTTPS
  4. Configure firewall rules
  → https://your-domain.com


N8N INTEGRATION STEPS:
======================

1. HTTP Request Node Configuration:
   - Method: POST
   - URL: http://your-server:8000/analyze
   - Body Content Type: JSON
   - Body: {"url": "{{ $json.website_url }}"}

2. Process Results Node:
   - Loop through {{ $json.issues }}
   - Extract: title, description, recommendation
   - Optional: Save screenshot_base64 to file storage

3. Send Results:
   - Email with formatted issues
   - Slack message with recommendations
   - Save to Google Sheets/Airtable
   - Create Jira/Linear tickets


PERFORMANCE CHARACTERISTICS:
=============================

Average Response Time: 10-20 seconds
  - Browser launch: 1-2s
  - Page load: 3-8s
  - Screenshot capture: 1-2s
  - Claude analysis: 5-10s
  - Response formatting: <1s

Resource Usage:
  - Memory: ~200-500 MB per request
  - CPU: Moderate (browser rendering + AI inference)
  - Network: ~1-5 MB per request (depends on webpage size)

Scaling Considerations:
  - Single instance: ~3-6 concurrent requests
  - For higher volume: Use task queue (Celery + Redis)
  - Consider caching results for repeated URLs
"""

print(__doc__)
