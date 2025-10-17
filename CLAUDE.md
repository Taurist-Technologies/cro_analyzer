# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CRO Analyzer is a FastAPI backend service that captures website screenshots using Playwright and analyzes them with Claude AI (Anthropic) to identify Conversion Rate Optimization (CRO) issues. The service is designed to integrate seamlessly with n8n workflows.

## Commands

### Development

```bash
# Always use python3 (per global config)
python3 main.py                                  # Start development server on port 8000
uvicorn main:app --reload --host 0.0.0.0 --port 8000  # Start with auto-reload
```

### Testing

```bash
python3 test_service.py                          # Run test suite (must be running service first)
curl http://localhost:8000/health                # Quick health check
```

### Setup & Installation

```bash
python3 -m venv venv                             # Create virtual environment
source venv/bin/activate                         # Activate venv (Windows: venv\Scripts\activate)
./setup.sh                                       # Automated setup (installs deps + Playwright)
pip install -r requirements.txt                  # Manual dependency install
playwright install chromium                      # Install Playwright browsers
export ANTHROPIC_API_KEY='sk-ant-...'           # Set API key (required)
```

### Docker

```bash
docker build -t cro-analyzer .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=xxx cro-analyzer
```

## Architecture

### Request Flow

1. **POST /analyze** receives a URL in JSON format
2. **Playwright** launches headless Chromium browser (1920x1080 viewport)
3. **Screenshot capture** takes full-page screenshot, resizes if > 7500px (Claude limit)
4. **Claude API** receives screenshot + analysis prompt via Anthropic SDK
5. **Response parsing** extracts 2-3 CRO issues from Claude's JSON response
6. **Response formatting** returns JSON with issues + base64 screenshots

### Core Components

- **main.py** - FastAPI application with three key functions:
  - `capture_screenshot_and_analyze()` - Main analysis workflow (lines 74-183)
  - `resize_screenshot_if_needed()` - Image resizing for Claude's 8000px limit (lines 41-71)
  - `/analyze` endpoint - Public API (lines 195-204)

- **test_service.py** - Test script that validates health endpoint and runs full analysis, saving screenshots and JSON results

- **setup.sh** - Automated setup script that checks Python version, creates venv, installs dependencies, and validates API key

### Key Technical Details

- **Model**: `claude-sonnet-4-20250514` with 2000 max tokens
- **Browser**: Chromium headless, waits for `networkidle`, 30s timeout
- **Image Processing**: Auto-resize images > 7500px using Pillow (LANCZOS resampling) to meet Claude's 8000px dimension limit
- **Response Time**: 10-20 seconds per analysis (browser launch + page load + AI inference)
- **Concurrency**: ~3-6 concurrent requests per instance (single Playwright browser per request)

### Data Models (Pydantic)

- `AnalysisRequest` - Contains validated HttpUrl
- `CROIssue` - Contains title, description, recommendation, optional screenshot_base64
- `AnalysisResponse` - Contains url, analyzed_at timestamp, list of issues

## Environment Variables

- `ANTHROPIC_API_KEY` (required) - Get from https://console.anthropic.com/

## API Endpoints

- `GET /` - Service info
- `POST /analyze` - Main analysis endpoint (accepts JSON: `{"url": "https://example.com"}`)
- `GET /health` - Health check (returns `{"status": "healthy"}`)
- `GET /docs` - Auto-generated Swagger UI docs

## CRO Analysis Focus Areas

The Claude prompt specifically targets:
- Above-the-fold value proposition clarity
- Call-to-action (CTA) visibility and contrast
- Trust signals and social proof
- Mobile responsiveness issues
- Form design and friction points
- Navigation and user flow

## Customization Points

### Modify Analysis Focus

Edit the prompt in `main.py` (lines 116-145) to target specific industries:
- E-commerce checkout optimization
- B2B lead generation forms
- SaaS pricing page effectiveness

### Adjust Screenshot Settings

- **Viewport size**: Change `viewport={'width': 1920, 'height': 1080}` (line 81)
- **Max dimension**: Modify `max_dimension=7500` parameter (line 42)
- **Wait time**: Adjust `wait_for_timeout(2000)` (line 89) for dynamic content

### Limit Issue Count

Change slice in line 175: `analysis_data["issues"][:3]` to return fewer issues

## Integration with n8n

The service is designed for n8n workflow integration:
- Use HTTP Request node with POST method
- URL: `http://your-server:8000/analyze`
- Body: `{"url": "{{ $json.website_url }}"}`
- Process response issues in loop
- Output to email, Slack, database, etc.

## Common Issues

- **Port 8000 in use**: Change port with `--port 8001` flag
- **Playwright not installed**: Run `playwright install chromium`
- **API key missing**: Set `ANTHROPIC_API_KEY` environment variable
- **Timeout errors**: Increase timeout in `page.goto()` (line 86) from 30000ms
- **Image too large**: Automatic resizing handles this, but check Pillow is installed

## Performance Considerations

- Single instance handles 3-6 concurrent requests
- Consider adding Celery + Redis task queue for high volume
- Implement caching for repeated URL analysis
- Screenshots are 500KB-3MB depending on page complexity
- Claude API costs ~$0.02-0.04 per analysis

## Production Deployment

- Use Docker container with included Dockerfile
- Configure reverse proxy (nginx) for HTTPS
- Implement rate limiting (not included by default)
- Add URL validation/allowlisting for security
- Monitor memory usage (~200-500MB per request)
- Consider multiple instances behind load balancer

## Testing

The test script (`test_service.py`) validates both endpoints and saves:
- Individual issue screenshots as `issue_N_screenshot.png`
- Clean JSON results as `analysis_result.json` (without base64 data)
