# ChromaDB Migration Quick Reference

## Current Status

```
✅ Export from Cloud      → chromadb_backup.json (1,177 records, 10.39 MB)
✅ Scripts created         → export, import, verify, test
✅ VectorDBClient updated  → supports Cloud + Self-Hosted
🚧 Railway deployment      → WAITING FOR USER
```

---

## Quick Command Reference

### 1. Test Railway Connection (Do this first!)

```bash
source venv/bin/activate
python3 scripts/test_railway_connection.py
```

**Expected output:** ✅ CONNECTION TEST PASSED!

### 2. Import Data to Railway

```bash
python3 scripts/import_to_selfhosted.py --input chromadb_backup.json
```

**Expected:** 1,177 records imported in ~30 seconds

### 3. Verify Migration

```bash
# Quick check - should show 1,177 records
python3 -c "from utils.vector_db import VectorDBClient; db = VectorDBClient(); print(f'Total records: {db.collection.count()}')"
```

### 4. Complete Full Ingestion

```bash
python3 scripts/ingest_audits.py --local-dir sample_audits/
```

**Expected:** All 28 audits ingested (2,054 total issues)

---

## Environment Variables (.env)

Add these after Railway deployment:

```bash
# Railway ChromaDB (Self-Hosted)
CHROMA_HOST=chromadb-production-xxxx.up.railway.app
CHROMA_PORT=8000
CHROMA_SSL=true
CHROMA_AUTH_TOKEN=YOUR_TOKEN  # Optional

# Keep these as backup (legacy)
CHROMA_API_KEY=ck-7U8cCUG6JANd8hqBsGHLdUcaZLetFebW2nPM562LjkSn
CHROMA_TENANT=3d558316-7b79-4958-bbce-23867aa8961d
CHROMA_DATABASE=tt-audits
```

---

## Railway Deployment Steps

1. **Go to Railway:** https://railway.app/new
2. **Search for ChromaDB template**
3. **Configure:**
   - Set `IS_PERSISTENT=TRUE`
   - Mount volume at `/chroma/chroma`
   - Enable public networking
4. **Wait for deployment** (~2-3 minutes)
5. **Copy Railway URL** from settings

---

## Troubleshooting

### Connection refused?
```bash
# Test Railway endpoint manually
curl https://YOUR_RAILWAY_URL:8000/api/v1/heartbeat
```

### Import fails?
```bash
# Check Railway is set in .env
echo $CHROMA_HOST  # Should show Railway URL

# Verify .env is loaded
python3 -c "import os; print(f'Host: {os.getenv(\"CHROMA_HOST\")}')"
```

### Wrong backend?
```bash
# VectorDBClient auto-detects based on CHROMA_HOST
# If CHROMA_HOST is set → uses Railway
# If CHROMA_HOST is NOT set → uses Cloud

# To force Cloud (for testing):
unset CHROMA_HOST  # or remove from .env
```

---

## File Locations

- **Export backup:** `chromadb_backup.json` (10.39 MB)
- **Export script:** `scripts/export_chromadb_cloud.py`
- **Import script:** `scripts/import_to_selfhosted.py`
- **Test script:** `scripts/test_railway_connection.py`
- **Full guide:** `CHROMADB_MIGRATION_GUIDE.md`

---

## Migration Checklist

- [x] Export 1,177 records from Cloud
- [ ] Deploy ChromaDB on Railway **← YOU ARE HERE**
- [ ] Add Railway URL to `.env`
- [ ] Run `test_railway_connection.py` (verify)
- [ ] Run `import_to_selfhosted.py` (migrate data)
- [ ] Run `ingest_audits.py` (complete ingestion)
- [ ] Verify 2,054 total issues in database

**Time estimate:** 30-45 minutes

---

## Cost Comparison

| Plan | Storage Limit | Monthly Cost | Status |
|------|---------------|--------------|--------|
| ChromaDB Cloud Free | 300 records | $0 | ❌ At quota |
| ChromaDB Cloud Starter | Unlimited | $29 | ⚠️ Over-budget |
| **Railway Self-Hosted** | **Unlimited** | **$10-13** | ✅ **Recommended** |

**Savings:** $19/month ($228/year) vs Cloud Starter
