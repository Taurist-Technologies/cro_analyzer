# 🚀 Quick Start Guide - CRO Analyzer

Get up and running in 5 minutes!

## Step 1: Setup (2 minutes)

```bash
# Navigate to the project
cd cro_analyzer

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Run setup (installs everything)
./setup.sh
# Or manually:
# pip install -r requirements.txt
# playwright install chromium
```

## Step 2: Configure API Key (1 minute)

```bash
# Set your Anthropic API key
export ANTHROPIC_API_KEY='sk-ant-xxxxx'

# Or create .env file
cp .env.example .env
# Then edit .env and add your key
```

Get your API key: https://console.anthropic.com/

## Step 3: Start the Service (30 seconds)

```bash
python main.py
```

Server runs at: http://localhost:8000
API docs at: http://localhost:8000/docs

## Step 4: Test It (1 minute)

In a new terminal:

```bash
# Activate venv first
source venv/bin/activate

# Run test
python test_service.py
```

This will:
- ✅ Test the service health
- 🔍 Analyze a website (anthropic.com by default)
- 💾 Save screenshots and JSON results
- 📊 Display all findings

## Step 5: Integrate with n8n

### Option A: Import Workflow
1. Open n8n
2. Go to **Workflows** → **Import from File**
3. Select `n8n_workflow_example.json`
4. Update the HTTP Request URL if not running locally

### Option B: Manual Setup
1. Add **HTTP Request** node
2. Configure:
   - Method: `POST`
   - URL: `http://localhost:8000/analyze`
   - Body: `{"url": "https://example.com"}`

## Quick Test from Command Line

```bash
# Test with cURL
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"url": "https://stripe.com"}'
```

## Troubleshooting

**Service won't start?**
- Check API key: `echo $ANTHROPIC_API_KEY`
- Check port: `lsof -i :8000` (kill if needed)

**Playwright errors?**
```bash
playwright install chromium
```

**Import errors?**
```bash
pip install -r requirements.txt
```

## What You Get

For each analyzed website:
- ✅ 2-3 specific CRO issues
- 📝 Clear descriptions
- 💡 Actionable recommendations
- 📸 Full-page screenshots (base64)
- ⚡ JSON response ready for n8n

## Example Response

```json
{
  "url": "https://example.com",
  "analyzed_at": "2025-10-17T10:30:00",
  "issues": [
    {
      "title": "Weak Above-Fold Value Proposition",
      "description": "Visitors can't understand the core offering within 5 seconds",
      "recommendation": "Add a benefit-focused headline that addresses user pain points",
      "screenshot_base64": "iVBORw0KG..."
    }
  ]
}
```

## Production Deployment

### Docker (Recommended)
```bash
docker build -t cro-analyzer .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=xxx cro-analyzer
```

### Cloud Platforms
- **Railway**: Connect GitHub repo, add API key env var
- **DigitalOcean App Platform**: Deploy from GitHub
- **AWS EC2/Fargate**: Use Docker image
- **Render**: Deploy Python app with environment variables

## Resources

- 📖 Full docs: `README.md`
- 🏗️ Architecture: `ARCHITECTURE.py`
- 🧪 Testing: `test_service.py`
- 🐳 Docker: `Dockerfile`
- 🔗 n8n integration: `n8n_workflow_example.json`

## Support

Questions? Check:
1. README.md for detailed docs
2. https://docs.anthropic.com for API help
3. https://playwright.dev/python for Playwright issues

---

**You're all set!** 🎉

Start analyzing websites and improving conversions!
