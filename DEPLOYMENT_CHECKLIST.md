# Render Deployment Checklist

Quick reference checklist for deploying CRO Analyzer to Render. See [RENDER_DEPLOYMENT_GUIDE.md](RENDER_DEPLOYMENT_GUIDE.md) for detailed instructions.

---

## Pre-Deployment

- [ ] Code pushed to GitHub/GitLab
- [ ] Have Anthropic API key ready
- [ ] Render account created
- [ ] Decided on plan tier (Starter $14/mo or Standard $89/mo)

---

## Step 1: Redis/Key Value

- [ ] Click **"New"** button → Select **"Key Value"** (or "Redis")
- [ ] Create instance: `cro-analyzer-redis`
- [ ] Choose region (e.g., Oregon US West)
- [ ] Select plan (Free for dev, Starter $7/mo for prod)
- [ ] Leave IP Allow List empty (internal-only access)
- [ ] Wait for "Available" status
- [ ] Copy **Internal Connection String**: `redis://red-xxxxx:6379` (no password)

**Internal Connection String**: `________________________________`

📝 **Note**: Use the **Internal** Connection String (no password) for all services

---

## Step 2: Environment Variables

- [ ] Create Environment Group: `cro-analyzer-env`
- [ ] Add variables:

```bash
ANTHROPIC_API_KEY=sk-ant-_______________
REDIS_URL=redis://red-xxxxx:6379
CELERY_BROKER_URL=redis://red-xxxxx:6379
CELERY_RESULT_BACKEND=redis://red-xxxxx:6379
CELERY_WORKER_CONCURRENCY=5
API_WORKERS=2
BROWSER_POOL_SIZE=5
BROWSER_MAX_PAGES=10
BROWSER_TIMEOUT=300
CACHE_TTL=86400
```

- [ ] Save Environment Group

---

## Step 3: API Server

- [ ] Create Web Service: `cro-analyzer-api`
- [ ] Connect Git repository
- [ ] Select branch: `main` or `development`
- [ ] Runtime: Docker
- [ ] Instance: Starter ($7) or Standard ($25)
- [ ] Link Environment Group: `cro-analyzer-env`
- [ ] Health Check Path: `/health`
- [ ] Enable Auto-Deploy
- [ ] Create service
- [ ] Wait for deploy (~5-10 min)
- [ ] Note public URL

**API URL**: `https://________________________________`

- [ ] Test health: `curl {API_URL}/health`
- [ ] Test status: `curl {API_URL}/status/detailed`

---

## Step 4: Worker Service

- [ ] Create Background Worker: `cro-analyzer-worker`
- [ ] Connect same repository
- [ ] Same branch as API
- [ ] Runtime: Docker
- [ ] Docker Command:
  ```bash
  celery -A celery_app worker --loglevel=info --concurrency=5 --max-tasks-per-child=50
  ```
- [ ] Instance: Starter ($7) or Standard ($25)
- [ ] Link Environment Group: `cro-analyzer-env`
- [ ] Add extra variable: `WORKER_MODE=true`
- [ ] Create service
- [ ] Wait for deploy (~5-10 min)
- [ ] Check logs for "celery@... ready"

---

## Step 5: Flower Monitoring (Optional)

- [ ] Create Web Service: `cro-analyzer-flower`
- [ ] Connect same repository
- [ ] Docker Command: `celery -A celery_app flower --port=5555`
- [ ] Instance: Starter ($7)
- [ ] Link Environment Group
- [ ] Optional: Add `FLOWER_BASIC_AUTH=admin:password`
- [ ] Create service

**Flower URL**: `https://________________________________`

---

## Step 6: Verify System

- [ ] All services show "Live" or "Available" status
- [ ] API `/health` returns `{"status": "healthy"}`
- [ ] API `/status/detailed` shows:
  - `"redis": "connected"`
  - `"celery": "workers_active"`
  - `"overall_status": "healthy"`
- [ ] Worker logs show "celery@... ready"
- [ ] Flower dashboard accessible (if deployed)

---

## Step 7: End-to-End Test

Run this test to verify the full async workflow:

```bash
# 1. Submit task
curl -X POST https://your-api.onrender.com/analyze/async \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "deep_info": true}'

# Copy task_id from response

# 2. Poll status (repeat until SUCCESS)
curl https://your-api.onrender.com/analyze/status/{task_id}

# 3. Get result
curl https://your-api.onrender.com/analyze/result/{task_id}
```

- [ ] Task submitted successfully (got task_id)
- [ ] Status changed from PENDING → STARTED → SUCCESS
- [ ] Result retrieved with CRO issues
- [ ] Total time: 10-50 seconds

---

## Step 8: Scaling (Optional)

For higher traffic:

- [ ] Scale workers: Settings → Scaling → Instance Count = 3-5
- [ ] Increase concurrency: Update `CELERY_WORKER_CONCURRENCY=10`
- [ ] Increase API workers: Update `API_WORKERS=4`
- [ ] Enable auto-scaling: Min=2, Max=10, CPU threshold=70%

---

## Step 9: Production Hardening

- [ ] Custom domain configured (if needed)
- [ ] CORS configured in code (if needed)
- [ ] Alerts enabled for all services
- [ ] Flower basic auth enabled
- [ ] Redis upgraded to paid plan with persistence
- [ ] Auto-scaling configured
- [ ] Monitoring dashboard bookmarked

---

## Step 10: Documentation

- [ ] API URL documented for team
- [ ] n8n workflow updated with new URL
- [ ] Flower credentials saved securely
- [ ] Environment variables backed up
- [ ] Deployment process documented

---

## Ongoing Monitoring

### Daily
- [ ] Check Flower for failed tasks
- [ ] Monitor error rates

### Weekly
- [ ] Review Redis memory usage
- [ ] Check worker utilization
- [ ] Review API response times

### Monthly
- [ ] Review costs vs. usage
- [ ] Update dependencies
- [ ] Optimize worker count

---

## Cost Summary

**Minimum (Dev/Testing):**
- Redis: Free
- API: $7/mo
- Worker: $7/mo
- **Total: $14/mo**

**Recommended (Production):**
- Redis: $7/mo
- API: $25/mo
- Worker x2: $50/mo
- Flower: $7/mo
- **Total: $89/mo**

**High-Volume:**
- Redis: $30/mo
- API x2: $50/mo
- Worker x5: $125/mo
- Flower: $7/mo
- **Total: $212/mo**

Plus Anthropic API: ~$0.02-0.04 per analysis (50% saved by caching)

---

## Troubleshooting Quick Fixes

### Workers Not Processing Tasks
```bash
# Check worker is running
# In Render: Go to worker service → Logs
# Should see: "celery@... ready"

# Restart worker service if needed
```

### Redis Connection Issues
```bash
# Verify Redis URL matches in all services
# Check Redis status is "Available"
# Restart API and worker services
```

### High Memory Usage
```bash
# Reduce CELERY_WORKER_CONCURRENCY to 3
# Reduce BROWSER_POOL_SIZE to 3
# Upgrade to Standard plan
```

---

## Emergency Rollback

1. Go to service → "Deploys" tab
2. Find last working deploy
3. Click "Rollback"
4. Confirm

---

## Support Contacts

- **Render Support**: https://render.com/docs/support
- **Render Status**: https://status.render.com
- **Team Lead**: ________________
- **On-Call Engineer**: ________________

---

## Service URLs Reference

Fill in after deployment:

| Service | URL | Status |
|---------|-----|--------|
| API | https://cro-analyzer-api.onrender.com | ☐ Live |
| Flower | https://cro-analyzer-flower.onrender.com | ☐ Live |
| Redis | redis://red-xxxxx:6379 | ☐ Available |
| Worker | Background (no URL) | ☐ Live |

---

## Deployment Date

- **Initial Deploy**: ________________
- **Production Ready**: ________________
- **Last Updated**: ________________
- **Deployed By**: ________________

---

## Sign-Off

- [ ] All services deployed and tested
- [ ] End-to-end workflow verified
- [ ] Monitoring and alerts configured
- [ ] Team notified of new API URL
- [ ] Documentation updated
- [ ] Production ready ✅

**Signed Off By**: ________________
**Date**: ________________

---

## Quick Commands Reference

```bash
# Health check
curl https://your-api.onrender.com/health

# Detailed status
curl https://your-api.onrender.com/status/detailed

# Submit async analysis
curl -X POST https://your-api.onrender.com/analyze/async \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# Check task status
curl https://your-api.onrender.com/analyze/status/{task_id}

# Get result
curl https://your-api.onrender.com/analyze/result/{task_id}
```

Save this checklist and mark items as you complete them! ✅
