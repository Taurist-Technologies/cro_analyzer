# ChromaDB Cloud → Self-Hosted Migration Guide

## Overview

This guide walks through migrating from ChromaDB Cloud (with 300-record quota) to self-hosted ChromaDB on Railway (unlimited storage).

**Current Status:**
- ✅ Exported 1,177 records from ChromaDB Cloud to `chromadb_backup.json`
- ✅ Created import script for self-hosted migration
- ✅ Updated VectorDBClient to support both Cloud and Self-Hosted
- ⏸️ **BLOCKED**: Waiting for Railway deployment

**Why Migrate:**
- ChromaDB Cloud Starter plan: 300-record ADD quota (BLOCKING)
- Only 6/28 audits ingested (1,177 issues) before quota hit
- 22 audits (877 issues) remain blocked
- Self-hosted: No quotas, only pay for compute/storage

---

## Step 1: Export from ChromaDB Cloud ✅ COMPLETE

Already completed! File saved as `chromadb_backup.json` (10.39 MB, 1,177 records).

<details>
<summary>Export breakdown by client</summary>

```
- Client Copy: PayNearMe: 273 records
- Hibernate Audit Documentation: 231 records
- Retrospec CRO Audit Documentation Internal: 196 records
- The Nutrition Insider CRO Audit: 187 records
- Internal Copy Jet Ski Cozumel CRO Audit: 178 records
- Annabella: 112 records
```
</details>

---

## Step 2: Deploy ChromaDB on Railway 🚧 USER ACTION REQUIRED

### Railway Deployment

Railway offers a one-click deployment template for ChromaDB:

1. **Go to Railway Dashboard:**
   - Visit: https://railway.app/new
   - Sign in with GitHub

2. **Deploy ChromaDB Template:**
   - Search for "ChromaDB" in templates
   - OR use direct link: https://railway.app/template/chromadb
   - Click "Deploy Now"

3. **Configure Deployment:**
   - **Project Name:** `cro-analyzer-chromadb`
   - **Service Name:** `chromadb`
   - **Environment Variables:**
     - `IS_PERSISTENT=TRUE` (enables data persistence)
     - `CHROMA_SERVER_AUTHN_CREDENTIALS=<generate-secure-token>` (optional auth)
     - `CHROMA_SERVER_AUTHN_PROVIDER=chromadb.auth.token_authn.TokenAuthenticationServerProvider` (if using auth)

4. **Configure Volume (Critical!):**
   - Mount path: `/chroma/chroma`
   - Size: Start with 1 GB (auto-scales)
   - This ensures data persists across restarts

5. **Deploy & Wait:**
   - Railway will build and deploy (2-3 minutes)
   - Wait for "Deployed" status

6. **Get Connection Details:**
   - Click on service → "Settings" → "Public Networking"
   - Enable public networking if not enabled
   - Copy the Railway URL (e.g., `chromadb-production-xxxx.up.railway.app`)
   - Default port: `8000`
   - SSL: `true` (Railway uses HTTPS)

### Cost Estimate

- **Compute:** ~$8-10/month for 1GB RAM instance (sufficient for 2K+ vectors)
- **Storage:** ~$2-3/month for 1GB volume
- **Total:** ~$10-13/month vs $29/month for ChromaDB Cloud Starter

---

## Step 3: Test Railway Connection

After Railway deployment completes, test the connection:

```bash
# Test heartbeat endpoint
curl https://chromadb-production-xxxx.up.railway.app:8000/api/v1/heartbeat

# Expected response:
{"nanosecond heartbeat": 1234567890123456789}
```

If you configured authentication:
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://chromadb-production-xxxx.up.railway.app:8000/api/v1/heartbeat
```

---

## Step 4: Update Environment Variables

Add Railway connection details to `.env`:

```bash
# Add these lines to .env (keep existing Cloud credentials as backup)
CHROMA_HOST=chromadb-production-xxxx.up.railway.app
CHROMA_PORT=8000
CHROMA_SSL=true
CHROMA_AUTH_TOKEN=YOUR_TOKEN  # Optional, only if you enabled auth
```

**Important:** The VectorDBClient will auto-detect which backend to use:
- If `CHROMA_HOST` is set → Uses HttpClient (self-hosted)
- If `CHROMA_HOST` is NOT set → Uses CloudClient (legacy)

---

## Step 5: Import Data to Self-Hosted Instance

Run the import script:

```bash
# Make sure venv is activated
source venv/bin/activate

# Run import
python3 scripts/import_to_selfhosted.py --input chromadb_backup.json
```

**What this does:**
1. Loads 1,177 records from `chromadb_backup.json`
2. Connects to Railway ChromaDB using HttpClient
3. Creates `cro_audit_issues` collection
4. Imports records in batches of 100
5. Verifies final count matches expected (1,177)

**Expected output:**
```
======================================================================
📥 CHROMADB SELF-HOSTED IMPORT
======================================================================

1️⃣ Loading backup from chromadb_backup.json...
   ✓ Loaded 1177 records
   Export date: 2025-01-10T...
   Collection: cro_audit_issues

2️⃣ Connecting to self-hosted ChromaDB...
   Host: chromadb-production-xxxx.up.railway.app
   Port: 8000
   SSL: true
   ✓ Connected successfully

3️⃣ Setting up collection...
   ✓ Collection ready: cro_audit_issues

4️⃣ Importing records...
   Batch 1: Imported 1-100
   Batch 2: Imported 101-200
   ...
   Batch 12: Imported 1101-1177

   ✓ Import complete: 1177/1177 records

5️⃣ Verifying import...
   Final record count: 1177
   ✓ Verification passed!

======================================================================
✅ IMPORT COMPLETE
======================================================================
```

---

## Step 6: Verify Migration

Run the verification script to ensure everything works:

```bash
python3 scripts/verify_vector_db.py
```

This will:
1. Connect to Railway ChromaDB
2. Check collection count (should be 1,177)
3. Test semantic search
4. Verify metadata integrity

---

## Step 7: Complete Full Ingestion

Now that quota limits are removed, ingest the remaining 22 audits:

```bash
python3 scripts/ingest_audits.py --local-dir sample_audits/
```

**Expected:**
- Start: 1,177 issues (from 6 audits)
- Add: 877 issues (from 22 remaining audits)
- **Total: 2,054 issues** from all 28 audits

**Timeline:** ~15-20 minutes (no quota blocking!)

---

## Rollback Plan (If Needed)

If Railway migration fails, you can revert to ChromaDB Cloud:

1. **Remove Railway env vars from .env:**
   ```bash
   # Comment out or remove these lines
   # CHROMA_HOST=...
   # CHROMA_PORT=...
   # CHROMA_SSL=...
   # CHROMA_AUTH_TOKEN=...
   ```

2. **VectorDBClient auto-reverts to CloudClient** (checks for `CHROMA_HOST` presence)

3. **Your 1,177 records are still in ChromaDB Cloud** (export didn't delete them)

---

## Troubleshooting

### Issue: "Connection refused" during import

**Cause:** Railway deployment not complete or URL incorrect

**Fix:**
1. Check Railway dashboard - service should show "Deployed" status
2. Verify URL in `.env` matches Railway service URL
3. Test heartbeat endpoint with curl (see Step 3)

### Issue: "Authentication failed"

**Cause:** Auth token mismatch or incorrectly configured

**Fix:**
1. If you enabled auth in Railway, ensure `CHROMA_AUTH_TOKEN` is set in `.env`
2. Verify token matches Railway env var `CHROMA_SERVER_AUTHN_CREDENTIALS`
3. Check header format: `Authorization: Bearer YOUR_TOKEN`

### Issue: Import fails with "Collection already exists"

**Cause:** Previous import attempt created collection

**Fix:**
1. Script will prompt: "Delete and recreate? (y/N)"
2. Answer `y` to delete and start fresh
3. Or answer `N` to append to existing collection

### Issue: "Count mismatch" after import

**Cause:** Batch import partially failed

**Fix:**
1. Check import script output for failed batches
2. Re-run import script (it's idempotent if you delete existing collection)
3. Check Railway logs for errors: `railway logs --service chromadb`

---

## Next Steps After Migration

1. **Monitor Railway usage:**
   - Dashboard: https://railway.app/project/your-project/metrics
   - Check memory/storage usage
   - Set up billing alerts

2. **Update backup strategy:**
   - Run export script weekly: `python3 scripts/export_chromadb_cloud.py`
   - Store backups in S3/Google Cloud Storage

3. **Consider upgrading compute:**
   - If performance is slow, increase RAM in Railway settings
   - Vector search benefits from more memory

4. **Clean up ChromaDB Cloud (Optional):**
   - After verifying Railway works for 1-2 weeks
   - Cancel ChromaDB Cloud subscription to save $29/month
   - Keep export file as backup

---

## Scripts Reference

### Created Scripts

1. **[scripts/export_chromadb_cloud.py](scripts/export_chromadb_cloud.py)**
   - Exports all records from ChromaDB Cloud to JSON
   - Handles 300-record GET quota with batching
   - Already executed: `chromadb_backup.json` created

2. **[scripts/import_to_selfhosted.py](scripts/import_to_selfhosted.py)**
   - Imports JSON backup to Railway ChromaDB
   - Batch imports (100 records per batch)
   - Interactive prompts for existing collections

3. **[scripts/verify_chroma_upgrade.py](scripts/verify_chroma_upgrade.py)**
   - Tests ChromaDB Cloud quota upgrade (if using Starter plan)
   - Adds/removes test records to verify quota increase
   - Alternative to Railway migration

### Updated Files

1. **[utils/vector_db.py](utils/vector_db.py)**
   - Added `_initialize_client()` method
   - Auto-detects Cloud vs Self-Hosted based on `CHROMA_HOST` env var
   - Supports both CloudClient and HttpClient

---

## Migration Status

- [x] Export from ChromaDB Cloud (1,177 records)
- [ ] Deploy ChromaDB on Railway **← YOU ARE HERE**
- [ ] Update `.env` with Railway credentials
- [ ] Import 1,177 records to Railway
- [ ] Verify migration
- [ ] Complete full ingestion (22 remaining audits)

**Estimated Time Remaining:** 30-45 minutes

**Next Action:** Deploy ChromaDB on Railway using the instructions in Step 2.
