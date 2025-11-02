# CRO Analyzer - Render Production Deployment Guide

Complete step-by-step guide to deploy the CRO Analyzer service to Render with full async architecture (Redis + Celery + Browser Pool).

## Prerequisites

- [ ] Render account (free or paid): https://render.com
- [ ] GitHub/GitLab repository with this code
- [ ] Anthropic API key: https://console.anthropic.com/

## Architecture Overview

You'll deploy 4 services on Render:
1. **Redis/Key Value** - Cache and message queue (Valkey-based, Redis-compatible)
2. **API Server** - FastAPI web service (public)
3. **Celery Workers** - Background task processors (private)
4. **Flower** (optional) - Monitoring dashboard (private)

---

## Step 1: Create Redis/Key Value Instance

Render now uses **Valkey** (a Redis-compatible fork) for its Redis and Key Value services. Both options work identically for this deployment.

### 1.1 Navigate to Key Value
1. Log into Render Dashboard: https://dashboard.render.com/
2. Click the **"New"** button (top right of dashboard)
3. From the dropdown menu, select **"Key Value"** (or **"Redis"** - both create Valkey instances)

### 1.2 Configure Key Value Instance
- **Name**: `cro-analyzer-redis`
- **Region**: Choose closest to your users (e.g., `Oregon (US West)`)
- **Plan**:
  - **Development**: Free (25MB) - good for testing
  - **Production**: Starter ($7/mo, 256MB) or higher
- **Maxmemory Policy**: `allkeys-lru` (default - evict least recently used keys)
- **IP Allow List**: Leave empty `[]` for internal-only access (recommended for security)

### 1.3 Create and Copy Connection String
1. Click **"Create Key Value"** at the bottom
2. Wait for status to show **"Available"** (~1-2 minutes)
3. On the Key Value dashboard, find **"Internal Connection String"** section
4. **Copy the Internal Connection String** - it will look like:
   ```
   redis://red-xxxxxxxxxxxxx:6379
   ```

   📝 **Note**: Internal connections are **unauthenticated by default** (no password in URL)

   ⚠️ **IMPORTANT**: Save this URL - you'll need it for all services!

### 1.4 Connection String Formats (For Reference)
- **Internal (use this)**: `redis://red-xxxxxxxxxxxxx:6379`
  - No authentication required
  - Only accessible from within your Render services
  - Faster and more secure

- **External (don't use for this deployment)**: `rediss://default:PASSWORD@red-xxxxxxxxxxxxx:6379`
  - Requires authentication with password
  - Accessible from outside Render
  - SSL/TLS encrypted (note the `rediss://` instead of `redis://`)

---

## Step 2: Create Environment Group (Recommended)

This allows you to share environment variables across all services.

### 2.1 Create Environment Group
1. Go to **"Environment Groups"** in left sidebar
2. Click **"New Environment Group"**
3. Name: `cro-analyzer-env`

### 2.2 Add Environment Variables

Click **"Add Environment Variable"** for each:

#### Required Variables
```bash
# Anthropic API Key (get from https://console.anthropic.com/)
ANTHROPIC_API_KEY=sk-ant-api03-your-actual-key-here

# Redis URLs (paste the Internal Redis URL from Step 1.3)
REDIS_URL=redis://red-xxxxxxxxxxxxx:6379
CELERY_BROKER_URL=redis://red-xxxxxxxxxxxxx:6379
CELERY_RESULT_BACKEND=redis://red-xxxxxxxxxxxxx:6379

# Worker Configuration
CELERY_WORKER_CONCURRENCY=5
API_WORKERS=2

# Browser Pool Configuration
BROWSER_POOL_SIZE=5
BROWSER_MAX_PAGES=10
BROWSER_TIMEOUT=300

# Cache Configuration
CACHE_TTL=86400
```

### 2.3 Save Environment Group
Click **"Save"** at the bottom

---

## Step 3: Deploy API Server (Web Service)

### 3.1 Create Web Service
1. Click **"New +"** → **"Web Service"**
2. Connect your Git repository:
   - Click **"Connect Repository"**
   - Authorize GitHub/GitLab if needed
   - Select your repository (`cro_analyzer`)
   - Click **"Connect"**

### 3.2 Configure Web Service

**Basic Settings:**
- **Name**: `cro-analyzer-api`
- **Region**: Same as Redis (e.g., `Oregon`)
- **Branch**: `main` or `development`
- **Root Directory**: `.` (leave blank if code is at root)
- **Runtime**: `Docker`

**Build & Deploy:**
- **Dockerfile Path**: `./Dockerfile` (auto-detected)
- **Docker Command**: Leave empty (uses default from Dockerfile)
  - Default: `uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2`

**Instance Type:**
- **Development**: Starter ($7/mo, 512MB RAM, 0.5 CPU)
- **Production**: Standard ($25/mo, 2GB RAM, 1 CPU) or higher
- ⚠️ **Note**: Each worker needs ~500MB RAM. Standard plan recommended for 2+ workers.

**Environment:**
1. Click **"Advanced"**
2. Under **"Environment"**, select your environment group: `cro-analyzer-env`
3. Or add variables manually (same as Step 2.2)

### 3.3 Advanced Settings

Scroll to **"Advanced"** section:

**Health Check Path:**
```
/health
```

**Auto-Deploy:**
- ✅ Enable "Auto-Deploy" (deploys on git push)

### 3.4 Create Service
1. Click **"Create Web Service"**
2. Wait for build and deploy (~5-10 minutes first time)
3. Watch logs for any errors
4. Once deployed, you'll see a **public URL** like:
   ```
   https://cro-analyzer-api.onrender.com
   ```

### 3.5 Test API Server
```bash
# Test health endpoint
curl https://cro-analyzer-api.onrender.com/health

# Test detailed status
curl https://cro-analyzer-api.onrender.com/status/detailed
```

Expected response:
```json
{
  "api": "healthy",
  "redis": "connected",
  "celery": "workers_active",
  "overall_status": "healthy"
}
```

---

## Step 4: Deploy Celery Workers (Background Workers)

### 4.1 Create Background Worker
1. Click **"New +"** → **"Background Worker"**
2. Select same repository as API server
3. Click **"Connect"**

### 4.2 Configure Worker Service

**Basic Settings:**
- **Name**: `cro-analyzer-worker`
- **Region**: Same as Redis and API
- **Branch**: Same as API (`main` or `development`)
- **Root Directory**: `.` (same as API)
- **Runtime**: `Docker`

**Build & Deploy:**
- **Dockerfile Path**: `./Dockerfile`
- **Docker Command** (⚠️ IMPORTANT - Override default):
  ```bash
  celery -A celery_app worker --loglevel=info --concurrency=5 --max-tasks-per-child=50
  ```

**Instance Type:**
- **Development**: Starter ($7/mo) - handles 3-5 concurrent tasks
- **Production**: Standard ($25/mo) - handles 10-15 concurrent tasks
- **High Volume**: Pro ($85/mo) - handles 20-30 concurrent tasks

**Environment:**
1. Click **"Advanced"**
2. Select environment group: `cro-analyzer-env`
3. **Add one additional variable**:
   - Key: `WORKER_MODE`
   - Value: `true`

### 4.3 Create Worker
1. Click **"Create Background Worker"**
2. Wait for build (~5-10 minutes)
3. Check logs for:
   ```
   [INFO/MainProcess] celery@... ready.
   [INFO/MainProcess] Connected to redis://...
   ```

### 4.4 Scale Workers (Optional)

For higher traffic, deploy multiple worker instances:

**Option A: Multiple Instances** (Recommended)
1. Go to worker service settings
2. Under **"Scaling"**, increase **"Instance Count"**:
   - Light traffic: 1-2 instances
   - Medium traffic: 3-5 instances
   - High traffic: 5-10 instances

**Option B: Duplicate Worker Service**
1. Create second worker: `cro-analyzer-worker-2`
2. Use same configuration
3. Deploy independently

---

## Step 5: Deploy Flower Monitoring (Optional)

Flower provides a web UI for monitoring Celery workers and tasks.

### 5.1 Create Flower Web Service
1. Click **"New +"** → **"Web Service"**
2. Connect same repository

### 5.2 Configure Flower Service

**Basic Settings:**
- **Name**: `cro-analyzer-flower`
- **Region**: Same as other services
- **Branch**: Same as other services
- **Runtime**: `Docker`

**Build & Deploy:**
- **Dockerfile Path**: `./Dockerfile`
- **Docker Command**:
  ```bash
  celery -A celery_app flower --port=5555
  ```

**Instance Type:**
- Starter ($7/mo) is sufficient

**Environment:**
- Select environment group: `cro-analyzer-env`

**Optional: Add Basic Auth** (Recommended for security)
Add additional environment variables:
```bash
FLOWER_BASIC_AUTH=admin:your-secure-password-here
```

### 5.3 Create and Access
1. Click **"Create Web Service"**
2. After deployment, access Flower at:
   ```
   https://cro-analyzer-flower.onrender.com
   ```
3. Login with credentials if you set `FLOWER_BASIC_AUTH`

---

## Step 6: Configure API for Public Access

### 6.1 Custom Domain (Optional)
1. Go to API service settings
2. Click **"Settings"** → **"Custom Domain"**
3. Add your domain (e.g., `api.yourcompany.com`)
4. Follow DNS configuration instructions
5. HTTPS is automatic via Let's Encrypt

### 6.2 CORS Configuration (if needed)

If you're calling the API from a web frontend, update `main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourfrontend.com"],  # Your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Commit and push to trigger auto-deploy.

---

## Step 7: Verify Full System

### 7.1 Check All Services Status
1. **Redis**: Status = "Available" (green)
2. **API**: Status = "Live" (green)
3. **Worker**: Status = "Live" (green)
4. **Flower** (if deployed): Status = "Live" (green)

### 7.2 Test End-to-End Flow

```bash
# Set your API URL
API_URL="https://cro-analyzer-api.onrender.com"

# Test 1: Health check
curl $API_URL/health

# Test 2: Detailed status
curl $API_URL/status/detailed

# Test 3: Submit async analysis
curl -X POST $API_URL/analyze/async \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "deep_info": true}'

# Note the task_id from response, then poll status:
TASK_ID="paste-task-id-here"
curl $API_URL/analyze/status/$TASK_ID

# After status shows "SUCCESS", get result:
curl $API_URL/analyze/result/$TASK_ID
```

### 7.3 Monitor Logs
```bash
# Watch API logs
render logs cro-analyzer-api --tail

# Watch worker logs
render logs cro-analyzer-worker --tail
```

Or view in Render Dashboard under each service's **"Logs"** tab.

---

## Step 8: Configure Auto-Scaling (Optional)

### 8.1 Worker Auto-Scaling
1. Go to worker service
2. Click **"Settings"** → **"Scaling"**
3. Configure:
   - **Min Instances**: 2
   - **Max Instances**: 10
   - **CPU Threshold**: 70%
   - **Memory Threshold**: 80%

### 8.2 API Auto-Scaling
Same process for API service:
- **Min Instances**: 1
- **Max Instances**: 5
- **CPU Threshold**: 70%

---

## Step 9: Set Up Monitoring & Alerts

### 9.1 Enable Render Health Checks
Already configured via `/health` endpoint.

### 9.2 Set Up Alerts (Render Dashboard)
1. Go to each service → **"Settings"** → **"Alerts"**
2. Configure email notifications for:
   - Service crashes
   - High memory usage (>80%)
   - High CPU usage (>70%)
   - Deploy failures

### 9.3 Monitor Key Metrics

**Via Flower** (recommended):
- Active workers
- Task success/failure rates
- Task processing times
- Queue length

**Via Render Dashboard**:
- CPU usage
- Memory usage
- Request volume
- Error rates

---

## Step 10: Production Optimization

### 10.1 Redis Configuration
1. Go to Redis instance settings
2. Upgrade to paid plan if needed
3. Enable **"Persistence"** for data safety
4. Set **"Maxmemory Policy"** to `allkeys-lru`

### 10.2 Worker Configuration

Edit environment variables for optimal performance:

```bash
# Increase for high traffic
CELERY_WORKER_CONCURRENCY=10
BROWSER_POOL_SIZE=10

# Decrease for cost optimization
CACHE_TTL=172800  # 48 hours cache

# Restart workers after fewer tasks (better memory management)
# Edit Docker command:
celery -A celery_app worker --loglevel=info --concurrency=10 --max-tasks-per-child=20
```

### 10.3 API Configuration

```bash
# Increase API workers for high traffic
API_WORKERS=4
```

Update Docker command if needed (in API service settings):
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## Cost Estimation

### Minimum Setup (Development/Testing)
- Redis: **Free** (25MB limit)
- API Server: **$7/mo** (Starter)
- Worker: **$7/mo** (Starter)
- **Total: $14/mo**

### Recommended Setup (Production)
- Redis: **$7/mo** (Starter, 256MB)
- API Server: **$25/mo** (Standard, 2 workers)
- Worker x2: **$50/mo** (2x Standard instances)
- Flower: **$7/mo** (Starter)
- **Total: $89/mo**

### High-Volume Setup (50+ concurrent users)
- Redis: **$30/mo** (Pro, 1GB)
- API Server x2: **$50/mo** (2x Standard)
- Worker x5: **$125/mo** (5x Standard)
- Flower: **$7/mo**
- **Total: $212/mo**

Plus Anthropic API costs (~$0.02-0.04 per analysis, 50% saved by caching).

---

## Troubleshooting

### Issue: Redis Connection Failed
**Symptoms**: API shows `"redis": "disconnected"` in `/status/detailed`

**Solution**:
1. ✅ **Verify you're using the Internal Connection String** (not External)
   - Internal format: `redis://red-xxxxx:6379` (no password)
   - External format: `rediss://default:PASSWORD@red-xxxxx:6379` (with password)
   - For internal Render services, always use Internal Connection String

2. Check Redis/Key Value status is "Available" in Render dashboard

3. Verify all three Redis URLs match in environment variables:
   - `REDIS_URL=redis://red-xxxxx:6379`
   - `CELERY_BROKER_URL=redis://red-xxxxx:6379`
   - `CELERY_RESULT_BACKEND=redis://red-xxxxx:6379`

4. Restart API and worker services to pick up changes

### Issue: No Workers Available
**Symptoms**: Tasks stuck in "PENDING" state

**Solution**:
1. Check worker service status is "Live"
2. View worker logs for errors
3. Verify `CELERY_BROKER_URL` matches `REDIS_URL`
4. Restart worker service

### Issue: Browser Pool Errors
**Symptoms**: Tasks fail with Playwright errors

**Solution**:
1. Increase worker memory (upgrade to Standard plan)
2. Decrease `BROWSER_POOL_SIZE` to 3
3. Check worker logs for specific Playwright errors
4. Verify Dockerfile installs Playwright correctly

### Issue: High Memory Usage
**Symptoms**: Worker crashes or OOM errors

**Solution**:
1. Reduce `CELERY_WORKER_CONCURRENCY` (try 3)
2. Reduce `BROWSER_POOL_SIZE` (try 3)
3. Add `--max-tasks-per-child=10` to worker command
4. Upgrade to larger instance type

### Issue: Slow Response Times
**Symptoms**: Tasks take >60 seconds

**Solution**:
1. Check Redis cache is working (`redis_stats` in `/status/detailed`)
2. Increase worker count (scale to 3-5 instances)
3. Verify browser pool is initialized
4. Check Anthropic API latency

---

## Maintenance

### Daily
- [ ] Check Flower dashboard for failed tasks
- [ ] Monitor error rates in Render dashboard

### Weekly
- [ ] Review Redis memory usage
- [ ] Check worker CPU/memory usage
- [ ] Review API response times
- [ ] Clear old cached results if needed

### Monthly
- [ ] Review and optimize worker count
- [ ] Update dependencies (security patches)
- [ ] Analyze cost vs. usage
- [ ] Review Anthropic API usage and costs

---

## Backup & Disaster Recovery

### Redis Backup
1. Render Redis includes automatic backups on paid plans
2. For manual backup, use Redis BGSAVE command
3. Cache data can be regenerated, so backups are optional

### Code Backup
- Your Git repository is the source of truth
- Render auto-deploys from Git
- Keep production branch stable

### Rollback Procedure
1. Go to service → **"Deploys"** tab
2. Find previous successful deploy
3. Click **"Rollback"**
4. Confirm rollback

---

## Security Checklist

- [ ] Store API keys in Render environment variables (not in code)
- [ ] Use Internal Redis URLs (not external)
- [ ] Enable Flower basic auth
- [ ] Keep Flower and worker services private (not public)
- [ ] Enable HTTPS on API (automatic with Render)
- [ ] Use secrets for sensitive environment variables
- [ ] Regularly update dependencies
- [ ] Monitor for unusual activity via Flower

---

## Support Resources

- **Render Docs**: https://render.com/docs
- **Render Status**: https://status.render.com
- **Render Community**: https://community.render.com
- **Celery Docs**: https://docs.celeryq.dev
- **Flower Docs**: https://flower.readthedocs.io
- **FastAPI Docs**: https://fastapi.tiangolo.com

---

## Next Steps

After deployment:
1. ✅ Test all endpoints with real URLs
2. ✅ Monitor Flower for task processing
3. ✅ Set up alerts and notifications
4. ✅ Document your API URL for n8n integration
5. ✅ Configure custom domain (optional)
6. ✅ Set up staging environment for testing

---

## Quick Reference Card

```bash
# Your Service URLs (update after deployment)
API_URL=https://cro-analyzer-api.onrender.com
FLOWER_URL=https://cro-analyzer-flower.onrender.com

# Health Checks
curl $API_URL/health
curl $API_URL/status/detailed

# Submit Analysis
curl -X POST $API_URL/analyze/async \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# Check Task Status
curl $API_URL/analyze/status/{task_id}

# Get Result
curl $API_URL/analyze/result/{task_id}

# Monitor Workers
open $FLOWER_URL
```

Save this card for quick access! 📋
