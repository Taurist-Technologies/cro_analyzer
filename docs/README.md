# CRO Analyzer Backend Service

A FastAPI backend service that uses Playwright and Claude (Anthropic AI) to analyze websites for Conversion Rate Optimization (CRO) issues.

## Features

- 📸 Captures full-page screenshots using Playwright
- 🤖 Analyzes websites with Claude's vision capabilities
- 🎯 Identifies 2-3 quick, actionable CRO issues
- 🔧 Returns specific recommendations with screenshots
- 🔌 Easy integration with n8n workflows

## Prerequisites

- Python 3.8+
- Anthropic API key

## Installation

1. **Clone or create the project directory:**
```bash
mkdir cro_analyzer
cd cro_analyzer
```

2. **Create a virtual environment:**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Install Playwright browsers:**
```bash
playwright install chromium
```

5. **Set up environment variables:**
```bash
export ANTHROPIC_API_KEY='your-api-key-here'
```

Or create a `.env` file:
```
ANTHROPIC_API_KEY=your-api-key-here
```

## Running the Service

**Development mode:**
```bash
python main.py
```

**Production mode with Uvicorn:**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

**With auto-reload (development):**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The service will be available at `http://localhost:8000`

## API Endpoints

### POST /analyze

Analyzes a website for CRO issues.

**Request:**
```json
{
  "url": "https://example.com"
}
```

**Response:**
```json
{
  "url": "https://example.com",
  "analyzed_at": "2025-10-17T10:30:00.000000",
  "issues": [
    {
      "title": "Weak Above-the-Fold Value Proposition",
      "description": "The homepage header doesn't clearly communicate what the product does within 5 seconds. Visitors are forced to scroll to understand the core offering.",
      "recommendation": "Add a clear, benefit-focused headline above the fold (e.g., 'Automate Your Workflow in 5 Minutes') with a subheadline that addresses the target audience's pain point.",
      "screenshot_base64": "iVBORw0KGgoAAAANS..."
    },
    {
      "title": "Low-Contrast CTA Button",
      "description": "The primary call-to-action button blends into the background with insufficient color contrast, making it easy to miss.",
      "recommendation": "Increase button contrast using a complementary color that stands out from the background. Ensure minimum 4.5:1 contrast ratio per WCAG guidelines.",
      "screenshot_base64": "iVBORw0KGgoAAAANS..."
    }
  ]
}
```

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy"
}
```

## Integration with n8n

### Method 1: HTTP Request Node

1. Add an **HTTP Request** node to your workflow
2. Configure:
   - **Method:** POST
   - **URL:** `http://your-server:8000/analyze`
   - **Body Content Type:** JSON
   - **Body:**
   ```json
   {
     "url": "{{ $json.website_url }}"
   }
   ```

### Method 2: Using n8n Webhook Trigger

```
[Webhook Trigger] → [HTTP Request to CRO Analyzer] → [Process Results] → [Send Email/Slack/etc]
```

Example n8n workflow:
1. **Webhook** - Receives website URL
2. **HTTP Request** - Calls `/analyze` endpoint
3. **Split Into Items** - Separates each issue
4. **Send Results** - Email, Slack, or save to database

## Usage Examples

### cURL Example
```bash
curl -X POST "http://localhost:8000/analyze" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

### Python Example
```python
import requests

response = requests.post(
    "http://localhost:8000/analyze",
    json={"url": "https://example.com"}
)

data = response.json()
for issue in data["issues"]:
    print(f"Issue: {issue['title']}")
    print(f"Description: {issue['description']}")
    print(f"Recommendation: {issue['recommendation']}")
    print("---")
```

### JavaScript/Node.js Example
```javascript
const response = await fetch('http://localhost:8000/analyze', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ url: 'https://example.com' })
});

const data = await response.json();
console.log(data);
```

## Docker Deployment (Optional)

Create a `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install --with-deps chromium

COPY main.py .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:
```bash
docker build -t cro-analyzer .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=your-key cro-analyzer
```

## Customization

### Adjust Analysis Focus

Modify the prompt in `main.py` to focus on specific CRO aspects:

```python
text = f"""You are a CRO expert. Focus specifically on:
- E-commerce checkout flow optimization
- B2B lead generation forms
- SaaS pricing page effectiveness
...
"""
```

### Change Screenshot Resolution

Adjust the viewport size in `main.py`:

```python
context = await browser.new_context(
    viewport={'width': 1920, 'height': 1080}  # Modify these values
)
```

### Limit to Specific Issues

The code already limits to 3 issues max. Adjust in `main.py`:

```python
for issue in analysis_data["issues"][:2]  # Change to 2 issues
```

## Troubleshooting

**Issue:** Playwright browsers not installed
```bash
playwright install chromium
```

**Issue:** Port 8000 already in use
```bash
uvicorn main:app --port 8001  # Use different port
```

**Issue:** Timeout errors
- Increase timeout in `page.goto()`:
```python
await page.goto(str(url), wait_until='networkidle', timeout=60000)
```

**Issue:** ANTHROPIC_API_KEY not found
```bash
export ANTHROPIC_API_KEY='your-key'
# Or add to .env file
```

## Performance Notes

- Average analysis time: 10-20 seconds per website
- Consider implementing caching for frequently analyzed URLs
- For high-volume usage, consider adding a task queue (Celery/Redis)

## Security Considerations

- The service accepts any URL - consider adding URL validation/allowlisting
- Screenshots may contain sensitive information - handle with care
- Rate limit the endpoint in production environments
- Use HTTPS in production

## License

MIT

## Support

For issues or questions, please refer to:
- Anthropic API docs: https://docs.anthropic.com
- Playwright docs: https://playwright.dev/python
- FastAPI docs: https://fastapi.tiangolo.com
