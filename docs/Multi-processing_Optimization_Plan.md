# Multi-processing Optimization

## Executive Summary

The CRO Analyzer currently supports 2-3 concurrent requests but is not optimized for production multi-user scenarios. This document outlines the current state, identifies bottlenecks, and provides a roadmap for scaling to handle 5-100+ concurrent users.

---

## Current State ✅ Partial Support

### What Works

**FastAPI Async Architecture**
- Application uses `async def` handlers enabling concurrent request handling
- Built on ASGI (Asynchronous Server Gateway Interface)
- Non-blocking I/O operations supported

**Async Playwright Implementation**
- Uses `async_playwright()` API for browser automation
- Each request spawns independent browser instance (line 288 in [main.py](main.py#L288))
- Prevents resource conflicts between concurrent requests

**Proper Cleanup**
- Browser instances properly closed in `finally` blocks (line 475 in [main.py](main.py#L475))
- No obvious memory leaks in happy path

### Current Performance Estimate

| Concurrent Users | Status | Expected Behavior |
|-----------------|--------|-------------------|
| 2-3 users | ✅ Works | May experience slight slowdown |
| 5-10 users | ⚠️ Degraded | Significant delays, possible timeouts |
| 10+ users | ❌ Fails | Timeouts, resource exhaustion, crashes |

**Per-request resource consumption:**
- Memory: 200-500MB per browser instance
- CPU: High during screenshot capture and image processing
- Time: 10-20 seconds per analysis
- Network: Claude API calls (synchronous blocking)

---

## Key Issues 🚨

### 1. Sequential Browser Launches
**Location:** Lines 288-290 in [main.py](main.py#L288-L290)

```python
browser = await p.chromium.launch(headless=True)
context = await browser.new_context(viewport={"width": 1920, "height": 1080})
page = await context.new_page()
```

**Problems:**
- Each request launches a new Chromium instance (~1-2 seconds startup overhead)
- Browser startup is pure overhead that doesn't contribute to analysis
- No browser instance pooling or reuse
- Cold start penalty on every request

**Impact:** Wastes 10-15% of total request time on browser initialization

### 2. No Concurrency Limits
**Location:** No rate limiting or request queue management implemented

**Problems:**
- FastAPI allows unlimited concurrent requests by default
- No maximum concurrent request enforcement
- No request queuing system
- Could accept more requests than system can handle

**Impact:** Under high load, server will accept all requests but fail to complete them, leading to cascading failures

### 3. Single Process Deployment
**Location:** Line 519 in [main.py](main.py#L519)

```python
uvicorn.run(app, host="0.0.0.0", port=8000, timeout_keep_alive=60)
```

**Problems:**
- Runs single Uvicorn process by default
- Does not leverage multi-core CPUs
- Python GIL (Global Interpreter Lock) limits CPU-bound operations to single core
- No horizontal scaling within single deployment

**Impact:** On a 4-core CPU, only utilizing ~25% of available processing power

### 4. Synchronous Claude API Calls
**Location:** Lines 310-337 in [main.py](main.py#L310-L337)

```python
message = anthropic_client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4000,  # Always uses 4000 tokens for section-based analysis
    messages=[...]
)
```

**Problems:**
- Using synchronous `anthropic.Anthropic()` client
- Blocks async event loop during API call
- Cannot efficiently handle concurrent Claude API requests
- Async client (`anthropic.AsyncAnthropic`) available but not used

**Impact:** 30-50% of request time spent blocking the event loop

### 5. Resource Cleanup Risks
**Location:** Throughout request lifecycle

**Problems:**
- No timeout enforcement on browser operations (page.goto has 60s timeout but no global limit)
- Long-running requests hold browser instances indefinitely
- No circuit breaker pattern for failing requests
- No graceful degradation under load

**Impact:** A few stuck requests can exhaust all available resources

### 6. Missing Production Features

**Not implemented:**
- Request rate limiting (per-IP or global)
- Response caching for repeated URLs
- Health check depth (only checks API availability, not system resources)
- Metrics/monitoring (request duration, queue depth, error rates)
- Request timeout middleware
- Graceful shutdown handling

---

## Recommended Solutions

### Option 1: Quick Win - Multi-worker Deployment ⚡
**Difficulty:** Easy | **Code Changes:** Minimal | **Improvement:** 2-3x throughput

**What it does:**
- Run multiple Uvicorn worker processes
- Each worker handles requests independently
- Leverages multi-core CPUs

**Implementation:**
```bash
# Update Dockerfile CMD
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

# Or for production with Gunicorn
gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

**Pros:**
- Zero code changes required
- Immediate performance improvement
- Works with existing codebase

**Cons:**
- Still launches new browser per request
- Multiplies resource consumption (4 workers = 4x memory)
- No request queuing or rate limiting

**Good for:** 5-10 concurrent users

**Files to modify:**
- [Dockerfile](Dockerfile#L54)
- [main.py](main.py#L519) (if running locally)

---

### Option 2: Browser Pooling + Rate Limiting 🎯
**Difficulty:** Medium | **Code Changes:** Moderate | **Improvement:** 3-5x throughput

**What it does:**
- Create pool of pre-launched browser instances
- Reuse browsers across requests
- Limit concurrent requests to prevent overload
- Add request timeout middleware

**Implementation overview:**
1. Browser pool manager with 3-5 warm browser instances
2. FastAPI dependency injection for browser acquisition
3. Semaphore-based rate limiting (max 5 concurrent)
4. Timeout middleware (60s max request time)

**Pros:**
- Eliminates browser launch overhead
- Predictable resource usage
- Prevents server overload
- Works well with existing architecture

**Cons:**
- Requires significant code refactoring
- Browser pool state management complexity
- Need to handle browser crashes/restarts

**Good for:** 10-20 concurrent users

**Files to create/modify:**
- New: `browser_pool.py` (browser pool manager)
- New: `middleware.py` (rate limiting and timeout)
- Modify: [main.py](main.py) (integrate pool and middleware)
- Modify: [requirements.txt](requirements.txt) (add `limits` or `slowapi`)

---

### Option 3: Full Async + Task Queue 🚀
**Difficulty:** Advanced | **Code Changes:** Significant | **Improvement:** 10x+ throughput

**What it does:**
- Convert to fully async architecture
- Background task processing with Celery/Redis
- Async Anthropic client
- Browser pool with health monitoring
- Webhook callbacks for long-running analyses

**Implementation overview:**
1. Add Redis for task queue and caching
2. Celery worker processes for background analysis
3. Convert `/analyze` endpoint to return task ID immediately
4. Add `/status/{task_id}` endpoint for polling
5. Optional webhook support for push notifications
6. Async Anthropic client for non-blocking API calls

**Architecture:**
```
Client -> FastAPI (accepts request, returns task_id)
       -> Redis (queue task)
       -> Celery Worker (processes analysis in background)
       -> Redis (stores result)
       -> Client polls /status/{task_id}
       -> FastAPI returns result
```

**Pros:**
- Highly scalable (50+ concurrent users)
- Non-blocking API responses
- Can retry failed tasks
- Result caching built-in
- Graceful degradation under load

**Cons:**
- Significant architecture change
- Requires Redis infrastructure
- More complex deployment
- Breaking API change (no longer synchronous)

**Good for:** 50+ concurrent users, production environments

**Files to create/modify:**
- New: `celery_app.py` (Celery configuration)
- New: `tasks.py` (background task definitions)
- New: `redis_client.py` (Redis connection management)
- Modify: [main.py](main.py) (async endpoints, task submission)
- Modify: [requirements.txt](requirements.txt) (add `celery`, `redis`, `asyncio-anthropic`)
- New: `docker-compose.yml` (multi-service orchestration)

---

### Option 4: Production-Ready Enterprise Solution 🏢
**Difficulty:** Expert | **Code Changes:** Extensive | **Improvement:** 50x+ throughput

**What it does:**
- Everything from Option 3, plus:
- Horizontal auto-scaling with Kubernetes
- Load balancer (nginx/HAProxy)
- Response caching layer (Redis)
- Monitoring (Prometheus + Grafana)
- Circuit breakers and retry logic
- Database for audit logs
- Multi-region deployment support

**Additional components:**
- **Kubernetes cluster** with HPA (Horizontal Pod Autoscaler)
- **Redis cluster** for caching and session management
- **PostgreSQL** for analysis history and audit logs
- **S3/Object storage** for screenshot archival
- **CloudFront/CDN** for cached responses
- **Datadog/New Relic** for APM monitoring
- **Sentry** for error tracking

**Pros:**
- Unlimited horizontal scaling
- High availability (99.9%+ uptime)
- Geographic distribution
- Advanced observability
- Production-grade reliability

**Cons:**
- Requires DevOps expertise
- Significant infrastructure costs
- Complex deployment pipeline
- Overkill for small/medium deployments

**Good for:** 100+ concurrent users, SaaS product, enterprise clients

**Files to create:**
- `kubernetes/deployment.yaml`
- `kubernetes/service.yaml`
- `kubernetes/hpa.yaml`
- `kubernetes/ingress.yaml`
- `terraform/` (infrastructure as code)
- `monitoring/prometheus.yml`
- `monitoring/grafana-dashboard.json`

---

## Comparison Matrix

| Feature | Current | Option 1 | Option 2 | Option 3 | Option 4 |
|---------|---------|----------|----------|----------|----------|
| Max Concurrent Users | 2-3 | 5-10 | 10-20 | 50+ | 100+ |
| Browser Reuse | ❌ | ❌ | ✅ | ✅ | ✅ |
| Multi-worker | ❌ | ✅ | ✅ | ✅ | ✅ |
| Rate Limiting | ❌ | ❌ | ✅ | ✅ | ✅ |
| Background Tasks | ❌ | ❌ | ❌ | ✅ | ✅ |
| Auto-scaling | ❌ | ❌ | ❌ | ❌ | ✅ |
| Caching | ❌ | ❌ | ❌ | ✅ | ✅ |
| Monitoring | ❌ | ❌ | ❌ | ⚠️ | ✅ |
| Code Changes | - | Minimal | Moderate | Significant | Extensive |
| Infrastructure | Single container | Single container | Single container | Multi-service | K8s cluster |
| Setup Time | - | 15 min | 2-4 hours | 1-2 days | 1-2 weeks |
| Monthly Cost | $0 | $0 | $0 | ~$50 (Redis) | $500+ |

---

## Implementation Recommendations by Use Case

### Scenario 1: Internal Tool / Low Traffic
**Users:** < 5 concurrent
**Recommended:** **Option 1** (Multi-worker)
**Why:** Minimal effort, adequate performance, no infrastructure complexity

### Scenario 2: Small Business / n8n Integration
**Users:** 5-20 concurrent
**Recommended:** **Option 2** (Browser Pool + Rate Limiting)
**Why:** Best balance of performance, complexity, and cost

### Scenario 3: SaaS Product / API Service
**Users:** 20-100 concurrent
**Recommended:** **Option 3** (Async + Task Queue)
**Why:** Scalable architecture, professional API design, manageable complexity

### Scenario 4: Enterprise / High-Volume Platform
**Users:** 100+ concurrent
**Recommended:** **Option 4** (Full Production Stack)
**Why:** Proven at scale, enterprise-grade reliability, worth the investment

---

## Questions for Decision Making

### 1. Expected Load
**How many concurrent users do you expect?**
- [ ] Light (2-5 concurrent requests)
- [ ] Medium (5-20 concurrent requests)
- [ ] Heavy (20-50 concurrent requests)
- [ ] Enterprise (50+ concurrent requests)

### 2. Deployment Environment
**Where will this application run?**
- [ ] Local development / single server
- [ ] Docker container (single instance)
- [ ] Docker Compose (multi-service)
- [ ] Cloud VM (AWS EC2, DigitalOcean, etc.)
- [ ] Kubernetes / container orchestration
- [ ] Managed platform (Heroku, Render, Railway)

### 3. Response Time Requirements
**What response time is acceptable?**
- [ ] 10-20 seconds is fine (current performance)
- [ ] Need < 10 seconds (requires optimization)
- [ ] Need < 5 seconds (requires aggressive caching)
- [ ] Real-time (< 2 seconds) - not feasible with current approach

### 4. Infrastructure Constraints
**What are your limitations?**
- [ ] Limited RAM (< 4GB available)
- [ ] Limited budget (prefer free/cheap solutions)
- [ ] Need to keep it simple (minimal dependencies)
- [ ] Can add external services (Redis, databases, etc.)
- [ ] Have DevOps resources available
- [ ] No constraints / enterprise environment

### 5. API Design Preference
**How should the API behave under load?**
- [ ] Synchronous (wait for result, current behavior)
- [ ] Asynchronous (return task ID, poll for result)
- [ ] Webhook callbacks (push results when ready)
- [ ] Hybrid (fast results sync, slow results async)

### 6. Caching Acceptable?
**Can you cache results for repeated URLs?**
- [ ] Yes, cache for 24 hours
- [ ] Yes, cache for 7 days
- [ ] Yes, but user can force refresh
- [ ] No, always fresh analysis required

### 7. Development Timeline
**How quickly do you need this implemented?**
- [ ] Immediate (today/tomorrow) → Option 1
- [ ] This week → Option 2
- [ ] This month → Option 3
- [ ] No rush / proper planning → Option 4

---

## Next Steps

1. **Answer the questions above** to determine optimal approach
2. **Review the recommended option** based on your answers
3. **Confirm the implementation plan** before starting development
4. **Execute in phases** if choosing Options 3 or 4:
   - Phase 1: Multi-worker deployment (quick win)
   - Phase 2: Browser pooling and rate limiting
   - Phase 3: Task queue and async processing
   - Phase 4: Monitoring and auto-scaling

---

## Additional Resources

### Useful Tools
- **Load Testing:** `locust`, `k6`, `ab` (Apache Bench)
- **Monitoring:** Prometheus + Grafana, Datadog
- **Task Queues:** Celery, RQ (Redis Queue), Dramatiq
- **Rate Limiting:** `slowapi`, `fastapi-limiter`
- **Caching:** Redis, Memcached

### FastAPI Performance Guides
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
- [FastAPI Performance Tips](https://fastapi.tiangolo.com/async/)
- [Uvicorn Workers](https://www.uvicorn.org/settings/#development)

### Playwright Optimization
- [Playwright Best Practices](https://playwright.dev/docs/best-practices)
- [Browser Context Pooling](https://playwright.dev/docs/browser-contexts)

---

## Document History

| Date | Version | Changes |
|------|---------|---------|
| 2025-10-29 | 1.0 | Initial document creation |

