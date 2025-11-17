# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CRO Analyzer is a **high-performance FastAPI backend service** with **distributed task processing** that captures website screenshots using Playwright and analyzes them with Claude AI (Anthropic) to identify Conversion Rate Optimization (CRO) issues.

**Architecture**: Multi-service system with Redis for caching/queue, Celery for background processing, browser pooling for efficiency, and async/sync API modes.

**Scalability**: Handles 20-50+ concurrent users with horizontal worker scaling.

## Commands

### Development (Standalone Mode)

```bash
# Simple single-process mode (no Redis/Celery required)
python3 main.py                                  # Start sync API on port 8000
uvicorn main:app --reload --host 0.0.0.0 --port 8000  # With auto-reload
```

### Production (Multi-Service Mode)

```bash
# Full async architecture with Redis, Celery, and browser pooling
docker-compose up                                # Start all services (Redis, API, Workers, Flower)
docker-compose up --scale worker=5               # Scale to 5 workers
docker-compose down                              # Stop all services

# Individual service commands
docker-compose up redis                          # Redis only
docker-compose up api                            # API server only
docker-compose up worker                         # Celery worker only
docker-compose up flower                         # Monitoring UI (http://localhost:5555)
```

### Testing

```bash
python3 test_service.py                          # Interactive test suite with mode selection
# Options: 1=Quick health, 2=Sync analysis, 3=Async analysis, 4=Full test

curl http://localhost:8000/health                # Basic health check
curl http://localhost:8000/status/detailed       # Detailed status (Redis, Celery, Browser Pool)
```

### Setup & Installation

```bash
python3 -m venv venv                             # Create virtual environment
source venv/bin/activate                         # Activate venv (Windows: venv\Scripts\activate)
./setup.sh                                       # Automated setup (installs deps + Playwright)
pip install -r requirements.txt                  # Manual dependency install
playwright install chromium                      # Install Playwright browsers

# Environment configuration
cp .env.example .env                             # Copy template
nano .env                                        # Edit with your API keys
export ANTHROPIC_API_KEY='sk-ant-...'           # Set API key (required)
export REDIS_URL='redis://localhost:6379/0'     # Redis connection (for async mode)
```

### Docker

```bash
# Simple single-container deployment
docker build -t cro-analyzer .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=xxx cro-analyzer

# Multi-service production deployment
docker-compose build                             # Build all images
docker-compose up -d                             # Start in background
docker-compose logs -f worker                    # View worker logs
docker-compose ps                                # Check service status
```

## Architecture

### Two Operating Modes

#### 1. **Sync Mode** (Simple, Standalone)
- Single process, no Redis/Celery required
- POST `/analyze` blocks until analysis complete (10-20s)
- Good for development, low-traffic deployments
- Handles 2-3 concurrent requests per instance

#### 2. **Async Mode** (Production, Scalable)
- Multi-service architecture with Redis + Celery
- POST `/analyze/async` returns immediately with task_id
- Client polls GET `/analyze/status/{task_id}` for completion
- Horizontal scaling: add more workers
- Handles 20-50+ concurrent requests with 5+ workers
- Includes 24-hour Redis cache (saves 50% cost on duplicate URLs)
- Browser pooling eliminates 1-2s launch overhead

### Request Flow (Async Mode)

1. **Client POST /analyze/async** submits task → returns task_id immediately (< 100ms)
2. **Redis queue** stores task for worker pickup
3. **Celery worker** picks up task from queue
4. **Browser pool** provides pre-warmed Chromium instance (1920x1080 viewport)
5. **Screenshot capture** takes full-page screenshot, resizes if > 7500px
6. **Redis cache check** - returns cached result if URL analyzed in last 24 hours
7. **Claude API** analyzes screenshot with section-based analysis (always 4000 tokens)
8. **Response parsing** extracts 2-5 CRO issues from Claude's JSON with multi-layer repair
9. **Redis result storage** caches result + stores in Celery result backend
10. **Client polls** GET `/analyze/status/{task_id}` until status=SUCCESS
11. **Client retrieves** GET `/analyze/result/{task_id}` for final result

### Core Components

#### API Layer
- **main.py** - FastAPI application with dual API modes:
  - **Sync endpoints**: `/analyze` (blocking), `/health`, `/docs`
  - **Async endpoints**: `/analyze/async` (task submission), `/analyze/status/{task_id}` (polling), `/analyze/result/{task_id}` (result retrieval)
  - **Status endpoints**: `/status/detailed` (Redis, Celery, browser pool health)

#### Background Processing
- **celery_app.py** - Celery configuration with:
  - Task routing (default + priority queues)
  - Time limits (180s hard, 150s soft)
  - Worker settings (prefetch=1, max_tasks_per_child=10)
  - Monitoring signals and event handlers

- **tasks.py** - Background task definitions:
  - `analyze_website()` - Main analysis task with retry logic
  - `cleanup_old_results()` - Periodic cache cleanup
  - `get_pool_health()` - Browser pool monitoring

#### Infrastructure
- **redis_client.py** - Redis connection manager:
  - Analysis result caching (24-hour TTL)
  - Health checks and connection pooling
  - Key management utilities

- **browser_pool.py** - Browser instance manager:
  - Pre-warmed browser pool (default: 5 instances)
  - Automatic recycling (max 10 pages or 5 minutes)
  - Health monitoring and statistics

#### Testing & Setup
- **test_service.py** - Interactive test suite:
  - Mode 1: Health checks only
  - Mode 2: Sync analysis test
  - Mode 3: Async analysis test with polling
  - Mode 4: Full test suite

- **setup.sh** - Automated setup script
- **docker-compose.yml** - Multi-service orchestration

### Key Technical Details

- **Model**: `claude-sonnet-4-20250514` with 4000 max tokens (section-based analysis)
- **Browser**: Chromium headless with anti-bot detection args
- **Browser Pool**: 5 pre-warmed instances, auto-recycling, saves 1-2s per request
- **Cache Strategy**: Redis 24-hour TTL, saves 50% API costs on duplicates
- **Image Processing**: Auto-resize images > 7500px using Pillow (LANCZOS resampling)
- **Response Time**:
  - Sync: 10-20 seconds (blocking)
  - Async: < 100ms task submission, 10-20s background processing
- **Concurrency**:
  - Sync mode: 2-3 concurrent requests per instance
  - Async mode: 20-50+ concurrent requests with 5 workers
  - Horizontal scaling: Linear with worker count
- **Retry Logic**: Exponential backoff for API failures (3 attempts, 2-10s wait)

### Data Models (Pydantic)

- `AnalysisRequest` - Contains validated HttpUrl
- `CROIssue` - Contains title, description, recommendation, optional screenshot_base64
- `AnalysisResponse` - Contains url, analyzed_at timestamp, list of issues

## Environment Variables

See [.env.example](.env.example) for full configuration. Key variables:

### Required
- `ANTHROPIC_API_KEY` - Get from https://console.anthropic.com/
- `REDIS_URL` - Redis connection (async mode only): `redis://localhost:6379/0`
- `CELERY_BROKER_URL` - Celery message broker (async mode): `redis://localhost:6379/0`
- `CELERY_RESULT_BACKEND` - Celery results (async mode): `redis://localhost:6379/1`

### Optional
- `WORKER_MODE` - Set to `true` for worker containers
- `CELERY_WORKER_CONCURRENCY` - Number of concurrent workers (default: 5)
- `API_WORKERS` - Uvicorn workers for API (default: 2)
- `BROWSER_POOL_SIZE` - Pre-warmed browsers (default: 5)
- `BROWSER_MAX_PAGES` - Max pages per browser (default: 10)
- `BROWSER_TIMEOUT` - Browser recycle timeout in seconds (default: 300)
- `CACHE_TTL` - Cache lifetime in seconds (default: 86400 = 24 hours)

## API Endpoints

### Core Endpoints
- `GET /` - Service info and documentation links
- `GET /health` - Basic health check (returns `{"status": "healthy"}`)
- `GET /status/detailed` - Detailed health check (Redis, Celery, browser pool)
- `GET /docs` - Auto-generated Swagger UI docs
- `GET /redoc` - Alternative API documentation

### Sync Endpoints (Blocking)
- `POST /analyze` - Analyze website (blocks 10-20s)
  - Request: `{"url": "https://example.com", "include_screenshots": false}`
  - Response: Full analysis result with issues

### Async Endpoints (Non-Blocking)
- `POST /analyze/async` - Submit analysis task (returns immediately)
  - Request: `{"url": "https://example.com", "include_screenshots": false}`
  - Response: `{"task_id": "abc-123", "status": "PENDING", "poll_url": "/analyze/status/abc-123"}`

- `GET /analyze/status/{task_id}` - Check task status (poll this)
  - Response: `{"task_id": "abc-123", "status": "PENDING|STARTED|SUCCESS|FAILURE"}`
  - If SUCCESS: includes `"result"` field with full analysis

- `GET /analyze/result/{task_id}` - Get completed result
  - Returns: Full analysis result if SUCCESS
  - Error 202: Task still processing
  - Error 404: Task not found

### Monitoring Endpoints (Async Mode Only)
- Flower UI at `http://localhost:5555` - Celery task monitoring, worker stats, task history

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

Edit the prompt in `analysis_prompt.py` to target specific industries:
- E-commerce checkout optimization
- B2B lead generation forms
- SaaS pricing page effectiveness

### Adjust Screenshot Settings

In `browser_pool.py` or `tasks.py`:
- **Viewport size**: Change `viewport={'width': 1920, 'height': 1080}`
- **Max dimension**: Modify `max_dimension=7500` parameter in `resize_screenshot_if_needed()`
- **Wait time**: Adjust `wait_for_timeout(2000)` for dynamic content

### Scaling Configuration

In `.env`:
- **Worker count**: Set `CELERY_WORKER_CONCURRENCY=10` for more parallelism
- **Browser pool**: Set `BROWSER_POOL_SIZE=10` for more pre-warmed browsers
- **Cache duration**: Set `CACHE_TTL=172800` for 48-hour cache

### Task Priority

Use priority queue for urgent requests:
```python
from tasks import analyze_website
task = analyze_website.apply_async(
    args=[url],
    queue='priority'  # Uses priority queue instead of default
)
```

## Integration with n8n

### Sync Mode Integration (Simple)
1. Use HTTP Request node with POST method
2. URL: `http://your-server:8000/analyze`
3. Body: `{"url": "{{ $json.website_url }}", "include_screenshots": false}`
4. Timeout: 30 seconds (allows for 10-20s analysis)
5. Process response issues in loop
6. Output to email, Slack, database, etc.

### Async Mode Integration (Scalable)
1. **Submit Task** - HTTP Request node (POST):
   - URL: `http://your-server:8000/analyze/async`
   - Body: `{"url": "{{ $json.website_url }}", "include_screenshots": false}`
   - Save `{{ $json.task_id }}` to variable

2. **Poll Status** - Loop with HTTP Request node (GET):
   - URL: `http://your-server:8000/analyze/status/{{ $json.task_id }}`
   - Wait 2 seconds between polls
   - Exit loop when `{{ $json.status }} === "SUCCESS"`

3. **Get Result** - HTTP Request node (GET):
   - URL: `http://your-server:8000/analyze/result/{{ $json.task_id }}`
   - Process `{{ $json.result.issues }}` array

4. **Output** - Use Switch/IF nodes to route to:
   - Email (SMTP node)
   - Slack (Slack API node)
   - Database (PostgreSQL/MySQL node)
   - Google Sheets (Google Sheets node)

## Common Issues

### Sync Mode
- **Port 8000 in use**: Change port with `--port 8001` flag or in docker-compose.yml
- **Playwright not installed**: Run `playwright install chromium --with-deps`
- **API key missing**: Set `ANTHROPIC_API_KEY` environment variable
- **Timeout errors**: Increase timeout in `page.goto()` from 90000ms
- **Image too large**: Automatic resizing handles this, check Pillow is installed

### Async Mode
- **Redis connection refused**: Start Redis with `docker-compose up redis` or install locally
- **No workers available**: Start workers with `docker-compose up worker` or `celery -A celery_app worker`
- **Task stuck in PENDING**: Check worker logs, ensure workers are running
- **Browser pool exhausted**: Increase `BROWSER_POOL_SIZE` in .env
- **Redis memory full**: Check cache size, adjust `maxmemory` in docker-compose.yml
- **Flower not accessible**: Ensure port 5555 is exposed and not blocked

### Debugging
```bash
# Check Redis connection
redis-cli -h localhost -p 6379 ping

# Check Celery workers
celery -A celery_app inspect active

# View real-time logs
docker-compose logs -f worker
docker-compose logs -f api

# Check browser pool health
curl http://localhost:8000/status/detailed
```

## Performance Metrics

### Sync Mode
- Concurrency: 2-3 requests per instance
- Response time: 10-20 seconds (blocking)
- Memory: 200-500MB per request
- Cost: $0.02-0.04 per analysis

### Async Mode
- Concurrency: 20-50+ requests (with 5 workers)
- Task submission: < 100ms
- Background processing: 10-20 seconds
- Cache hit rate: ~50% (24-hour TTL)
- Cost reduction: 50% from caching
- Memory: 200-500MB per worker + 256MB Redis
- Horizontal scaling: Linear with worker count

### Optimization Tips
- **Browser pooling**: Saves 1-2s per request
- **Redis caching**: Saves 50% API costs on duplicates
- **Worker scaling**: Add workers for linear throughput increase
- **Connection pooling**: Redis client uses connection pool
- **Retry logic**: Exponential backoff for transient failures

## Production Deployment

### Docker Compose (Recommended)
```bash
# 1. Configure environment
cp .env.example .env
nano .env  # Set ANTHROPIC_API_KEY and adjust settings

# 2. Build images
docker-compose build

# 3. Start services
docker-compose up -d

# 4. Scale workers as needed
docker-compose up -d --scale worker=10

# 5. Monitor with Flower
open http://localhost:5555
```

### Render Deployment

**📚 Complete Deployment Guides:**
- **[RENDER_DEPLOYMENT_GUIDE.md](RENDER_DEPLOYMENT_GUIDE.md)** - Comprehensive step-by-step guide (10 steps)
- **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)** - Quick reference checklist with sign-off

**Quick Overview:**
1. Create Redis Instance → Copy Internal Redis URL
2. Create Environment Group → Add all env vars (see [.env.example](.env.example))
3. Deploy API Service (Web Service) → Enable health check at `/health`
4. Deploy Worker Service (Background Worker) → Set `WORKER_MODE=true`
5. Deploy Flower (Optional) → Monitoring dashboard at port 5555
6. Verify & Test → Run end-to-end async test

**Cost Estimates:**
- **Dev/Testing**: $14/mo (Free Redis + Starter API + Starter Worker)
- **Production**: $89/mo (Starter Redis + Standard API + 2x Standard Workers + Flower)
- **High-Volume**: $212/mo (Pro Redis + 2x Standard API + 5x Standard Workers + Flower)

See deployment guides for detailed instructions, troubleshooting, cost optimization, and security best practices.

### Production Checklist
- [ ] Use environment groups for shared config
- [ ] Enable Redis persistence (appendonly yes)
- [ ] Configure Redis maxmemory-policy (allkeys-lru)
- [ ] Set up monitoring (Flower, Datadog, New Relic)
- [ ] Implement rate limiting (nginx, API gateway)
- [ ] Add URL validation/allowlisting
- [ ] Enable HTTPS with reverse proxy
- [ ] Set up log aggregation (Papertrail, CloudWatch)
- [ ] Configure auto-scaling for workers
- [ ] Set resource limits in docker-compose.yml
- [ ] Regular health checks and alerting
- [ ] Backup Redis data if persistence is critical

### Security Best Practices
- Store API keys in secrets manager (not .env in production)
- Use Redis AUTH password in production
- Restrict Redis access to internal network only
- Implement API authentication (JWT, API keys)
- Use HTTPS for all external traffic
- Regularly update dependencies
- Monitor for unusual activity

## Monitoring

### Health Checks
```bash
# Basic health
curl http://localhost:8000/health

# Detailed status (all components)
curl http://localhost:8000/status/detailed

# Celery worker stats
celery -A celery_app inspect stats

# Redis info
redis-cli INFO stats
```

### Flower Dashboard
- URL: http://localhost:5555
- Features:
  - Real-time worker monitoring
  - Task history and states
  - Worker resource usage
  - Task rate graphs
  - Task routing visualization

### Key Metrics to Monitor
- **API**: Response times, error rates, request volume
- **Workers**: Active tasks, task success/failure rates, worker uptime
- **Redis**: Memory usage, cache hit rate, connection count
- **Browser Pool**: Available browsers, recycle rate, page count
- **Claude API**: Token usage, API latency, rate limit status

## Testing

The interactive test script (`test_service.py`) offers 4 modes:
1. **Quick (Mode 1)**: Health checks only (< 1 second)
2. **Sync (Mode 2)**: Blocking analysis test (10-20 seconds)
3. **Async (Mode 3)**: Non-blocking analysis with polling (10-20 seconds)
4. **Full (Mode 4)**: All tests (20-40 seconds)

Output files:
- `sync_issue_N_screenshot.png` - Screenshots from sync test
- `async_issue_N_screenshot.png` - Screenshots from async test
- `analysis_result_sync.json` - Sync test results (clean JSON, no base64)
- `analysis_result_async.json` - Async test results (clean JSON, no base64)
