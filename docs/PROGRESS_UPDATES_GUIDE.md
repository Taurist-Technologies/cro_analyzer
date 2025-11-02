# Real-Time Progress Updates Guide

## Overview

This guide explains how to implement real-time progress updates for the CRO Analyzer to provide a better loading/waiting experience for users during the 10-20 second analysis process.

---

## Current Analysis Flow

Based on [tasks.py:101-243](tasks.py#L101-L243), the analysis process consists of 5 key steps:

| Step | Duration | Description | Code Location |
|------|----------|-------------|---------------|
| 1. Browser Acquisition | ~500ms | Getting browser from pool or launching new instance | [tasks.py:109-120](tasks.py#L109-L120) |
| 2. Page Loading | ~2-5s | Navigating to URL + waiting for dynamic content | [tasks.py:123-128](tasks.py#L123-L128) |
| 3. Screenshot Capture | ~1-2s | Taking full page screenshot + resizing if needed | [tasks.py:130-133](tasks.py#L130-L133) |
| 4. AI Analysis | ~5-10s | Sending to Claude API and waiting for response (longest step) | [tasks.py:142-150](tasks.py#L142-L150) |
| 5. Result Parsing | ~1-2s | Parsing JSON response and formatting issues | [tasks.py:152-243](tasks.py#L152-L243) |

**Total Time:** 10-20 seconds (varies by page complexity and AI response time)

**Current UX Problem:** Users only see PENDING → SUCCESS with no intermediate feedback.

---

## Implementation Options

### **Option 1: Celery Progress Updates** ⭐ RECOMMENDED

**Best for:** Production-grade real-time progress tracking with accurate step-by-step updates.

#### How It Works

Celery tasks can report progress using `self.update_state()` method:

```python
@celery_app.task(bind=True, base=CallbackTask)
def analyze_website(self, url: str, ...):
    # Step 1: Browser
    self.update_state(
        state='PROGRESS',
        meta={
            'current': 1,
            'total': 5,
            'percent': 20,
            'status': 'Acquiring browser from pool...'
        }
    )

    # ... do the work ...

    # Step 2: Page Loading
    self.update_state(
        state='PROGRESS',
        meta={
            'current': 2,
            'total': 5,
            'percent': 40,
            'status': 'Loading webpage...'
        }
    )

    # ... and so on for each step
```

The frontend polls the existing `/analyze/status/{task_id}` endpoint to get progress:

```javascript
async function pollProgress(taskId) {
    const response = await fetch(`/analyze/status/${taskId}`);
    const data = await response.json();

    if (data.state === 'PROGRESS') {
        // Update UI with progress
        updateProgressBar(data.info.percent, data.info.status);
    } else if (data.state === 'SUCCESS') {
        // Show results
        displayResults(data.result);
    }
}

// Poll every 1 second
const interval = setInterval(() => pollProgress(taskId), 1000);
```

#### Pros & Cons

✅ **Pros:**
- Native Celery feature, no extra dependencies
- Works with existing polling endpoint
- Minimal code changes (5-10 lines per step)
- Progress stored in Redis automatically
- Accurate, real-time updates
- Works with current FastAPI + Celery setup

⚠️ **Cons:**
- Still requires polling (every 1-2 seconds)
- Slight Redis overhead per update (~100 bytes/update)
- Need to update both backend and frontend

#### Implementation Checklist

**Backend Changes:**

1. **[tasks.py:246-300](tasks.py#L246-L300)** - Update `analyze_website()` task signature:
   ```python
   @celery_app.task(bind=True, base=CallbackTask, name="tasks.analyze_website", ...)
   def analyze_website(self, url: str, include_screenshots: bool = False, deep_info: bool = False):
   ```

2. **[tasks.py:101-243](tasks.py#L101-L243)** - Add progress updates in `_capture_and_analyze_async()`:
   - Pass `task` parameter to function
   - Add 5 `task.update_state()` calls at each step

3. **[main.py:703-745](main.py#L703-L745)** - Update `/analyze/status/{task_id}` endpoint:
   ```python
   elif task.state == "PROGRESS":
       response["message"] = "Task is being processed"
       response["progress"] = task.info  # Contains meta dict
   ```

**Frontend Changes:**

1. Poll `/analyze/status/{task_id}` every 1 second
2. Check for `task.state === "PROGRESS"`
3. Read `task.info` for progress metadata
4. Update progress bar with `percent` and `status` message

#### Estimated Implementation Time

- Backend: 1-2 hours
- Frontend: 1 hour
- Testing: 30 minutes
- **Total: 2-3 hours**

---

### **Option 2: Server-Sent Events (SSE)**

**Best for:** True real-time updates without polling (push instead of pull).

#### How It Works

1. Backend creates SSE endpoint: `/analyze/stream/{task_id}`
2. Frontend opens EventSource connection
3. Backend pushes progress updates as they happen
4. Frontend receives updates instantly

```python
# Backend: New SSE endpoint
from fastapi.responses import StreamingResponse
import asyncio

@app.get("/analyze/stream/{task_id}")
async def stream_task_progress(task_id: str):
    async def event_stream():
        while True:
            # Get task status from Celery
            task = AsyncResult(task_id)

            if task.state == "PROGRESS":
                data = json.dumps(task.info)
                yield f"data: {data}\n\n"
            elif task.state in ["SUCCESS", "FAILURE"]:
                data = json.dumps({"state": task.state, "result": task.result})
                yield f"data: {data}\n\n"
                break

            await asyncio.sleep(0.5)  # Check every 500ms

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

```javascript
// Frontend: Listen to SSE
const eventSource = new EventSource(`/analyze/stream/${taskId}`);

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.percent) {
        updateProgressBar(data.percent, data.status);
    } else if (data.state === 'SUCCESS') {
        displayResults(data.result);
        eventSource.close();
    }
};

eventSource.onerror = () => {
    // Handle errors, auto-reconnect
    console.error('SSE connection error');
};
```

#### Pros & Cons

✅ **Pros:**
- True real-time (no polling delay)
- Less bandwidth than polling (push only when changed)
- Native browser support (EventSource API)
- Automatic reconnection on disconnect
- More responsive UX

⚠️ **Cons:**
- More complex backend (new endpoint + streaming logic)
- Requires keeping connection open (1 per client)
- More integration testing needed
- Potential scaling concerns (1 connection per user)
- Need to handle connection cleanup

#### Implementation Checklist

1. Install SSE support: `pip install sse-starlette`
2. Create new streaming endpoint
3. Implement event generator function
4. Update frontend to use EventSource API
5. Add error handling and reconnection logic

#### Estimated Implementation Time

- Backend: 2-3 hours
- Frontend: 1-2 hours
- Testing: 1 hour
- **Total: 4-6 hours**

---

### **Option 3: Smart Polling with Time-Based Estimates** 🚀 QUICK WIN

**Best for:** Immediate UX improvement with zero backend changes.

#### How It Works

Frontend calculates estimated progress based on elapsed time and shows stage-based messages:

```javascript
class AnalysisProgressTracker {
    constructor() {
        this.startTime = Date.now();
        this.stages = [
            { time: 0, percent: 0, message: 'Initializing...' },
            { time: 1, percent: 10, message: 'Acquiring browser...' },
            { time: 2, percent: 20, message: 'Loading webpage...' },
            { time: 5, percent: 40, message: 'Capturing screenshot...' },
            { time: 7, percent: 50, message: 'Analyzing with AI...' },
            { time: 12, percent: 80, message: 'Processing results...' },
            { time: 15, percent: 90, message: 'Finalizing...' },
        ];
    }

    getProgress() {
        const elapsed = (Date.now() - this.startTime) / 1000;

        // Find current stage
        let stage = this.stages[0];
        for (let i = this.stages.length - 1; i >= 0; i--) {
            if (elapsed >= this.stages[i].time) {
                stage = this.stages[i];
                break;
            }
        }

        // Interpolate between stages
        const nextStage = this.stages[this.stages.indexOf(stage) + 1];
        if (nextStage) {
            const progress = (elapsed - stage.time) / (nextStage.time - stage.time);
            const percent = stage.percent + (nextStage.percent - stage.percent) * progress;
            return { percent: Math.min(90, Math.round(percent)), message: stage.message };
        }

        return { percent: stage.percent, message: stage.message };
    }
}

// Usage
const tracker = new AnalysisProgressTracker();

const interval = setInterval(() => {
    const { percent, message } = tracker.getProgress();
    updateProgressBar(percent, message);

    // Still poll for actual completion
    checkTaskStatus(taskId).then(status => {
        if (status.state === 'SUCCESS') {
            clearInterval(interval);
            updateProgressBar(100, 'Complete!');
            displayResults(status.result);
        }
    });
}, 500);
```

#### React Example

```jsx
function AnalysisProgress({ taskId }) {
    const [progress, setProgress] = useState({ percent: 0, message: 'Starting...' });
    const trackerRef = useRef(new AnalysisProgressTracker());

    useEffect(() => {
        const interval = setInterval(() => {
            // Update estimated progress
            setProgress(trackerRef.current.getProgress());

            // Check real status
            fetch(`/analyze/status/${taskId}`)
                .then(r => r.json())
                .then(data => {
                    if (data.state === 'SUCCESS') {
                        clearInterval(interval);
                        setProgress({ percent: 100, message: 'Complete!' });
                        onComplete(data.result);
                    }
                });
        }, 500);

        return () => clearInterval(interval);
    }, [taskId]);

    return (
        <div>
            <div className="progress-bar">
                <div style={{ width: `${progress.percent}%` }} />
            </div>
            <p>{progress.message}</p>
        </div>
    );
}
```

#### Pros & Cons

✅ **Pros:**
- Zero backend changes required
- Immediate implementation (30 minutes)
- Better UX than plain spinner
- Works with all existing endpoints (sync and async)
- Easy to iterate and adjust timings
- No additional infrastructure needed

⚠️ **Cons:**
- Not accurate (just estimates)
- Can't adapt to actual progress
- May show 90% for longer than expected on slow sites
- No visibility into which step is actually running
- Can feel "fake" if timing is off

#### Implementation Checklist

1. Create progress tracker class/function
2. Define stage timings based on average analysis time
3. Update UI component to show progress bar
4. Add smooth animation/transition effects
5. Still poll for actual completion

#### Estimated Implementation Time

- Frontend: 30 minutes
- Testing: 15 minutes
- **Total: 45 minutes**

---

## Recommended Approach: Phased Implementation

### **Phase 1: Quick Win (Week 1)** 🚀

**Goal:** Improve UX immediately with minimal effort

1. Implement **Option 3** (Time-Based Estimates)
2. Test with users and gather feedback
3. Measure impact on perceived performance

**Deliverables:**
- Smooth progress bar showing estimated progress
- Stage-based messages ("Loading page...", "Analyzing with AI...")
- 30-45 minutes implementation time

### **Phase 2: Production Solution (Week 2-3)** 🎯

**Goal:** Add accurate, real-time progress tracking

1. Implement **Option 1** (Celery Progress Updates)
2. Update status endpoint to return progress metadata
3. Frontend detects and uses real progress when available
4. Keep time-based estimates as fallback

**Deliverables:**
- Accurate step-by-step progress
- Real-time status messages from backend
- 2-3 hours implementation time

### **Phase 3: Future Enhancement (Optional)** 🚀

**Goal:** True real-time with WebSocket/SSE

1. Evaluate if polling is causing issues
2. If needed, implement **Option 2** (SSE)
3. Migrate frontend to EventSource API
4. Remove polling logic

---

## Code Implementation Examples

### Backend: Celery Progress Updates (Option 1)

#### File: `tasks.py`

```python
@celery_app.task(
    bind=True,  # ← Add this to access self
    base=CallbackTask,
    name="tasks.analyze_website",
    max_retries=3,
    default_retry_delay=60,
)
def analyze_website(
    self, url: str, include_screenshots: bool = False, deep_info: bool = False
) -> dict:
    """
    Celery task to analyze a website for CRO issues with progress tracking.
    """
    task_id = self.request.id
    logger.info(f"🚀 Starting analysis task {task_id} for {url}")

    try:
        # Check cache first
        redis_client = get_redis_client()
        cached_result = redis_client.get_cached_analysis(url)

        if cached_result:
            logger.info(f"💾 Cache hit for {url}, returning cached result")
            return cached_result

        # Run async analysis in event loop with progress tracking
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _capture_and_analyze_async(
                    url, include_screenshots, deep_info, task=self  # ← Pass task instance
                )
            )
        finally:
            loop.close()

        # Cache the result (24 hours)
        redis_client.cache_analysis(url, result, ttl=86400)

        return result

    except anthropic.APIError as e:
        logger.error(f"❌ Anthropic API error for {url}: {str(e)}")
        raise self.retry(exc=e, countdown=60, max_retries=3)

    except Exception as e:
        logger.error(f"❌ Task failed for {url}: {str(e)}")
        raise


async def _capture_and_analyze_async(
    url: str, include_screenshots: bool = False, deep_info: bool = False, task=None
) -> dict:
    """
    Async function to capture screenshot and analyze with Claude.
    Now includes progress updates via task.update_state()
    """

    # STEP 1: Acquire browser (10% progress)
    if task:
        task.update_state(
            state='PROGRESS',
            meta={
                'current': 1,
                'total': 5,
                'percent': 10,
                'status': 'Acquiring browser from pool...',
                'url': url
            }
        )

    try:
        pool = await get_browser_pool(pool_size=5)
        browser, context, page = await pool.acquire()
        use_pool = True
    except Exception as e:
        logger.warning(f"⚠️  Browser pool unavailable, using standalone browser: {str(e)}")
        p = await async_playwright().start()
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        use_pool = False

    try:
        # STEP 2: Load page (30% progress)
        if task:
            task.update_state(
                state='PROGRESS',
                meta={
                    'current': 2,
                    'total': 5,
                    'percent': 30,
                    'status': f'Loading webpage: {url}',
                    'url': url
                }
            )

        logger.info(f"📡 Navigating to {url}")
        await page.goto(str(url), wait_until="load", timeout=90000)
        await page.wait_for_timeout(2000)

        # STEP 3: Capture screenshot (50% progress)
        if task:
            task.update_state(
                state='PROGRESS',
                meta={
                    'current': 3,
                    'total': 5,
                    'percent': 50,
                    'status': 'Capturing full page screenshot...',
                    'url': url
                }
            )

        logger.info(f"📸 Capturing screenshot of {url}")
        screenshot_bytes = await page.screenshot(full_page=True)
        screenshot_base64 = resize_screenshot_if_needed(screenshot_bytes)
        page_title = await page.title()
        logger.info(f"📄 Page title: {page_title}")

        # STEP 4: AI Analysis (70% progress)
        if task:
            task.update_state(
                state='PROGRESS',
                meta={
                    'current': 4,
                    'total': 5,
                    'percent': 70,
                    'status': 'Analyzing with Claude AI (this may take 5-10 seconds)...',
                    'url': url
                }
            )

        cro_prompt = get_cro_prompt(deep_info=deep_info)
        logger.info(f"🤖 Analyzing {url} with Claude AI...")
        message = call_anthropic_api_with_retry(
            screenshot_base64=screenshot_base64,
            cro_prompt=cro_prompt,
            url=str(url),
            page_title=page_title,
            deep_info=deep_info,
        )

        # STEP 5: Parse results (90% progress)
        if task:
            task.update_state(
                state='PROGRESS',
                meta={
                    'current': 5,
                    'total': 5,
                    'percent': 90,
                    'status': 'Processing and formatting results...',
                    'url': url
                }
            )

        response_text = message.content[0].text.strip()

        # Remove markdown code blocks if present
        if response_text.startswith("```json"):
            response_text = response_text.replace("```json", "").replace("```", "").strip()
        elif response_text.startswith("```"):
            response_text = response_text.replace("```", "").strip()

        # Extract JSON from response if wrapped in text
        if not response_text.startswith("{"):
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                response_text = response_text[start_idx : end_idx + 1]

        # Parse JSON with multi-layer repair
        analysis_data = repair_and_parse_json(response_text, deep_info=deep_info)

        # Build response based on format
        issues = []

        if deep_info:
            # Deep info format
            if "top_5_issues" in analysis_data:
                for issue in analysis_data["top_5_issues"][:5]:
                    issues.append({
                        "title": issue.get("issue_title", ""),
                        "description": (
                            issue.get("whats_wrong", "")
                            + "\n\nWhy it matters: "
                            + issue.get("why_it_matters", "")
                        ),
                        "recommendation": "\n".join(issue.get("implementation_ideas", [])),
                        "screenshot_base64": screenshot_base64 if include_screenshots else None,
                    })

            result = {
                "url": str(url),
                "analyzed_at": datetime.utcnow().isoformat(),
                "issues": issues,
                "total_issues_identified": analysis_data.get("total_issues_identified", len(issues)),
                "executive_summary": {
                    "overview": analysis_data.get("executive_summary", {}).get("overview", ""),
                    "how_to_act": analysis_data.get("executive_summary", {}).get("how_to_act", ""),
                },
                "cro_analysis_score": {
                    "score": analysis_data.get("cro_analysis_score", {}).get("score", 0),
                    "calculation": analysis_data.get("cro_analysis_score", {}).get("calculation", ""),
                    "rating": analysis_data.get("cro_analysis_score", {}).get("rating", ""),
                },
                "site_performance_score": {
                    "score": analysis_data.get("site_performance_score", {}).get("score", 0),
                    "calculation": analysis_data.get("site_performance_score", {}).get("calculation", ""),
                    "rating": analysis_data.get("site_performance_score", {}).get("rating", ""),
                },
                "conversion_rate_increase_potential": {
                    "percentage": analysis_data.get("conversion_rate_increase_potential", {}).get("percentage", ""),
                    "confidence": analysis_data.get("conversion_rate_increase_potential", {}).get("confidence", ""),
                    "rationale": analysis_data.get("conversion_rate_increase_potential", {}).get("rationale", ""),
                },
                "deep_info": True,
            }
        else:
            # Standard format (2-3 key points)
            accepted_prefixes = ["key point", "keypoint", "issue", "finding", "point"]
            logger.info(f"DEBUG: Keys received from Claude: {list(analysis_data.keys())}")

            for key, value in analysis_data.items():
                if isinstance(value, dict):
                    key_lower = key.lower().strip()
                    if any(key_lower.startswith(prefix) for prefix in accepted_prefixes):
                        logger.info(f"DEBUG: Matched key '{key}' as issue")
                        issues.append({
                            "title": key,
                            "description": value.get("Issue", "") or value.get("issue", "") or value.get("description", ""),
                            "recommendation": value.get("Recommendation", "") or value.get("recommendation", "") or value.get("solution", ""),
                            "screenshot_base64": screenshot_base64 if include_screenshots else None,
                        })

            result = {
                "url": str(url),
                "analyzed_at": datetime.utcnow().isoformat(),
                "issues": issues[:3],
                "deep_info": False,
            }

        logger.info(f"✅ Analysis complete for {url}: {len(issues)} issues found")
        return result

    finally:
        # Cleanup
        if use_pool:
            await pool.release(browser, context, page)
        else:
            await page.close()
            await context.close()
            await browser.close()
```

#### File: `main.py` - Update status endpoint

```python
@app.get("/analyze/status/{task_id}")
async def get_task_status(task_id: str):
    """
    Check the status of a background analysis task.

    Returns:
        - PENDING: Task is waiting in queue
        - STARTED: Task is being processed
        - PROGRESS: Task is in progress (includes progress metadata)
        - SUCCESS: Task completed successfully (includes result)
        - FAILURE: Task failed (includes error details)
        - RETRY: Task is being retried
    """
    try:
        from celery.result import AsyncResult

        task = AsyncResult(task_id)

        response = {
            "task_id": task_id,
            "status": task.state,
        }

        if task.state == "PENDING":
            response["message"] = "Task is waiting in queue"

        elif task.state == "STARTED":
            response["message"] = "Task is being processed"

        elif task.state == "PROGRESS":
            response["message"] = "Task is in progress"
            response["progress"] = task.info  # ← Contains progress metadata

        elif task.state == "SUCCESS":
            response["message"] = "Task completed successfully"
            response["result"] = task.result

        elif task.state == "FAILURE":
            response["message"] = "Task failed"
            response["error"] = str(task.info)

        elif task.state == "RETRY":
            response["message"] = "Task is being retried"
            response["retry_info"] = str(task.info)

        else:
            response["message"] = f"Unknown state: {task.state}"

        return response

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve task status: {str(e)}"
        )
```

---

### Frontend: Polling with Progress Display (Option 1)

#### Vanilla JavaScript

```javascript
class CROAnalyzer {
    constructor() {
        this.taskId = null;
        this.pollInterval = null;
    }

    async submitAnalysis(url, deepInfo = false) {
        const response = await fetch('/analyze/async', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: url,
                deep_info: deepInfo,
                include_screenshots: false
            })
        });

        const data = await response.json();
        this.taskId = data.task_id;

        // Start polling
        this.startPolling();

        return this.taskId;
    }

    startPolling() {
        this.pollInterval = setInterval(() => {
            this.checkStatus();
        }, 1000); // Poll every 1 second
    }

    async checkStatus() {
        const response = await fetch(`/analyze/status/${this.taskId}`);
        const data = await response.json();

        if (data.status === 'PROGRESS') {
            // Update progress bar
            const { percent, status, current, total } = data.progress;
            this.updateProgressBar(percent, status, current, total);

        } else if (data.status === 'SUCCESS') {
            // Analysis complete
            clearInterval(this.pollInterval);
            this.updateProgressBar(100, 'Complete!', 5, 5);
            this.displayResults(data.result);

        } else if (data.status === 'FAILURE') {
            // Analysis failed
            clearInterval(this.pollInterval);
            this.handleError(data.error);
        }
    }

    updateProgressBar(percent, status, current, total) {
        // Update DOM elements
        const progressBar = document.querySelector('.progress-bar-fill');
        const statusText = document.querySelector('.progress-status');
        const stepText = document.querySelector('.progress-step');

        progressBar.style.width = `${percent}%`;
        statusText.textContent = status;
        stepText.textContent = `Step ${current} of ${total}`;
    }

    displayResults(result) {
        // Display CRO analysis results
        console.log('Analysis complete:', result);
        // ... render results UI
    }

    handleError(error) {
        alert(`Analysis failed: ${error}`);
    }
}

// Usage
const analyzer = new CROAnalyzer();
analyzer.submitAnalysis('https://example.com', false);
```

#### React Hook

```jsx
import { useState, useEffect, useRef } from 'react';

function useAnalysisProgress(taskId) {
    const [progress, setProgress] = useState({
        percent: 0,
        status: 'Initializing...',
        current: 0,
        total: 5
    });
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [isComplete, setIsComplete] = useState(false);

    useEffect(() => {
        if (!taskId) return;

        const pollInterval = setInterval(async () => {
            try {
                const response = await fetch(`/analyze/status/${taskId}`);
                const data = await response.json();

                if (data.status === 'PROGRESS') {
                    setProgress(data.progress);

                } else if (data.status === 'SUCCESS') {
                    clearInterval(pollInterval);
                    setProgress({ percent: 100, status: 'Complete!', current: 5, total: 5 });
                    setResult(data.result);
                    setIsComplete(true);

                } else if (data.status === 'FAILURE') {
                    clearInterval(pollInterval);
                    setError(data.error);
                    setIsComplete(true);
                }
            } catch (err) {
                clearInterval(pollInterval);
                setError(err.message);
                setIsComplete(true);
            }
        }, 1000);

        return () => clearInterval(pollInterval);
    }, [taskId]);

    return { progress, result, error, isComplete };
}

// Component
function AnalysisProgress({ url }) {
    const [taskId, setTaskId] = useState(null);
    const { progress, result, error, isComplete } = useAnalysisProgress(taskId);

    const startAnalysis = async () => {
        const response = await fetch('/analyze/async', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, deep_info: false })
        });

        const data = await response.json();
        setTaskId(data.task_id);
    };

    return (
        <div className="analysis-container">
            {!taskId && (
                <button onClick={startAnalysis}>Start Analysis</button>
            )}

            {taskId && !isComplete && (
                <div className="progress-container">
                    <div className="progress-bar">
                        <div
                            className="progress-bar-fill"
                            style={{ width: `${progress.percent}%` }}
                        />
                    </div>
                    <p className="progress-status">{progress.status}</p>
                    <p className="progress-step">
                        Step {progress.current} of {progress.total}
                    </p>
                    <p className="progress-percent">{progress.percent}%</p>
                </div>
            )}

            {result && (
                <div className="results">
                    <h2>Analysis Complete!</h2>
                    <h3>{result.issues.length} Issues Found</h3>
                    {result.issues.map((issue, i) => (
                        <div key={i} className="issue-card">
                            <h4>{issue.title}</h4>
                            <p>{issue.description}</p>
                            <p><strong>Recommendation:</strong> {issue.recommendation}</p>
                        </div>
                    ))}
                </div>
            )}

            {error && (
                <div className="error">
                    <p>Analysis failed: {error}</p>
                </div>
            )}
        </div>
    );
}
```

#### Vue 3 Composition API

```vue
<template>
  <div class="analysis-container">
    <button v-if="!taskId" @click="startAnalysis">
      Start Analysis
    </button>

    <div v-if="taskId && !isComplete" class="progress-container">
      <div class="progress-bar">
        <div
          class="progress-bar-fill"
          :style="{ width: `${progress.percent}%` }"
        />
      </div>
      <p class="progress-status">{{ progress.status }}</p>
      <p class="progress-step">Step {{ progress.current }} of {{ progress.total }}</p>
      <p class="progress-percent">{{ progress.percent }}%</p>
    </div>

    <div v-if="result" class="results">
      <h2>Analysis Complete!</h2>
      <h3>{{ result.issues.length }} Issues Found</h3>
      <div
        v-for="(issue, i) in result.issues"
        :key="i"
        class="issue-card"
      >
        <h4>{{ issue.title }}</h4>
        <p>{{ issue.description }}</p>
        <p><strong>Recommendation:</strong> {{ issue.recommendation }}</p>
      </div>
    </div>

    <div v-if="error" class="error">
      <p>Analysis failed: {{ error }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onUnmounted } from 'vue';

const props = defineProps({
  url: String
});

const taskId = ref(null);
const progress = ref({
  percent: 0,
  status: 'Initializing...',
  current: 0,
  total: 5
});
const result = ref(null);
const error = ref(null);
const isComplete = ref(false);
let pollInterval = null;

const startAnalysis = async () => {
  const response = await fetch('/analyze/async', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: props.url, deep_info: false })
  });

  const data = await response.json();
  taskId.value = data.task_id;
};

const checkStatus = async () => {
  const response = await fetch(`/analyze/status/${taskId.value}`);
  const data = await response.json();

  if (data.status === 'PROGRESS') {
    progress.value = data.progress;

  } else if (data.status === 'SUCCESS') {
    clearInterval(pollInterval);
    progress.value = { percent: 100, status: 'Complete!', current: 5, total: 5 };
    result.value = data.result;
    isComplete.value = true;

  } else if (data.status === 'FAILURE') {
    clearInterval(pollInterval);
    error.value = data.error;
    isComplete.value = true;
  }
};

watch(taskId, (newTaskId) => {
  if (newTaskId) {
    pollInterval = setInterval(checkStatus, 1000);
  }
});

onUnmounted(() => {
  if (pollInterval) {
    clearInterval(pollInterval);
  }
});
</script>
```

---

### Frontend: Time-Based Estimates (Option 3)

#### Standalone Progress Tracker Class

```javascript
/**
 * AnalysisProgressTracker - Provides time-based progress estimates
 * for CRO analysis tasks when real-time progress isn't available.
 *
 * Usage:
 *   const tracker = new AnalysisProgressTracker();
 *   const { percent, message } = tracker.getProgress();
 */
class AnalysisProgressTracker {
    constructor(estimatedDuration = 15) {
        this.startTime = Date.now();
        this.estimatedDuration = estimatedDuration; // seconds

        // Define stages with timing (in seconds) and messages
        this.stages = [
            { time: 0, percent: 0, message: 'Initializing analysis...' },
            { time: 1, percent: 10, message: 'Acquiring browser...' },
            { time: 2, percent: 20, message: 'Loading webpage...' },
            { time: 5, percent: 40, message: 'Capturing screenshot...' },
            { time: 7, percent: 50, message: 'Analyzing with AI...' },
            { time: 12, percent: 80, message: 'Processing results...' },
            { time: 15, percent: 90, message: 'Finalizing...' },
        ];
    }

    /**
     * Get current progress based on elapsed time
     * @returns {Object} { percent: number, message: string, elapsed: number }
     */
    getProgress() {
        const elapsed = (Date.now() - this.startTime) / 1000;

        // Find current stage
        let currentStage = this.stages[0];
        let nextStage = this.stages[1];

        for (let i = this.stages.length - 1; i >= 0; i--) {
            if (elapsed >= this.stages[i].time) {
                currentStage = this.stages[i];
                nextStage = this.stages[i + 1] || currentStage;
                break;
            }
        }

        // Interpolate between stages for smooth progress
        let percent = currentStage.percent;
        if (nextStage && elapsed < nextStage.time) {
            const stageProgress = (elapsed - currentStage.time) / (nextStage.time - currentStage.time);
            const percentDiff = nextStage.percent - currentStage.percent;
            percent = currentStage.percent + (percentDiff * stageProgress);
        }

        return {
            percent: Math.min(90, Math.round(percent)), // Cap at 90% until real completion
            message: currentStage.message,
            elapsed: Math.round(elapsed)
        };
    }

    /**
     * Reset tracker to start new analysis
     */
    reset() {
        this.startTime = Date.now();
    }
}

// Usage Example
const tracker = new AnalysisProgressTracker();

const interval = setInterval(() => {
    const { percent, message, elapsed } = tracker.getProgress();

    // Update UI
    updateProgressBar(percent, message);
    console.log(`${elapsed}s: ${percent}% - ${message}`);

    // Still check for real completion
    checkTaskCompletion(taskId).then(isComplete => {
        if (isComplete) {
            clearInterval(interval);
            updateProgressBar(100, 'Complete!');
        }
    });
}, 500); // Update every 500ms for smooth animation
```

#### React Component with Estimates

```jsx
import { useState, useEffect, useRef } from 'react';

function AnalysisProgressWithEstimates({ taskId }) {
    const [progress, setProgress] = useState({ percent: 0, message: 'Starting...' });
    const [isComplete, setIsComplete] = useState(false);
    const [result, setResult] = useState(null);
    const trackerRef = useRef(null);

    useEffect(() => {
        // Initialize tracker
        trackerRef.current = new AnalysisProgressTracker(15);

        // Update estimated progress
        const estimateInterval = setInterval(() => {
            if (!isComplete) {
                const estimate = trackerRef.current.getProgress();
                setProgress(estimate);
            }
        }, 500);

        // Check real status
        const statusInterval = setInterval(async () => {
            try {
                const response = await fetch(`/analyze/status/${taskId}`);
                const data = await response.json();

                if (data.status === 'SUCCESS') {
                    clearInterval(estimateInterval);
                    clearInterval(statusInterval);
                    setProgress({ percent: 100, message: 'Complete!', elapsed: 0 });
                    setResult(data.result);
                    setIsComplete(true);
                } else if (data.status === 'FAILURE') {
                    clearInterval(estimateInterval);
                    clearInterval(statusInterval);
                    setIsComplete(true);
                    alert('Analysis failed: ' + data.error);
                }
            } catch (err) {
                console.error('Status check failed:', err);
            }
        }, 1000);

        return () => {
            clearInterval(estimateInterval);
            clearInterval(statusInterval);
        };
    }, [taskId, isComplete]);

    return (
        <div className="progress-container">
            {!isComplete && (
                <>
                    <div className="progress-bar">
                        <div
                            className="progress-bar-fill"
                            style={{
                                width: `${progress.percent}%`,
                                transition: 'width 0.5s ease' // Smooth animation
                            }}
                        />
                    </div>
                    <p className="progress-message">{progress.message}</p>
                    <p className="progress-percent">{progress.percent}%</p>
                    <p className="progress-elapsed">{progress.elapsed}s elapsed</p>
                </>
            )}

            {isComplete && result && (
                <div className="results">
                    {/* Display results */}
                </div>
            )}
        </div>
    );
}
```

---

## CSS Styling Examples

### Modern Progress Bar

```css
.progress-container {
    width: 100%;
    max-width: 600px;
    margin: 2rem auto;
    padding: 2rem;
    background: #f8f9fa;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.progress-bar {
    width: 100%;
    height: 12px;
    background: #e9ecef;
    border-radius: 6px;
    overflow: hidden;
    margin-bottom: 1rem;
    position: relative;
}

.progress-bar-fill {
    height: 100%;
    background: linear-gradient(90deg, #4CAF50, #45a049);
    border-radius: 6px;
    transition: width 0.3s ease;
    position: relative;
    overflow: hidden;
}

/* Animated shimmer effect */
.progress-bar-fill::after {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(
        90deg,
        transparent,
        rgba(255,255,255,0.3),
        transparent
    );
    animation: shimmer 2s infinite;
}

@keyframes shimmer {
    0% { left: -100%; }
    100% { left: 100%; }
}

.progress-status {
    font-size: 1rem;
    color: #495057;
    margin-bottom: 0.5rem;
    font-weight: 500;
}

.progress-step {
    font-size: 0.875rem;
    color: #6c757d;
    margin-bottom: 0.25rem;
}

.progress-percent {
    font-size: 2rem;
    font-weight: bold;
    color: #4CAF50;
    margin: 1rem 0;
    text-align: center;
}

.progress-elapsed {
    font-size: 0.875rem;
    color: #adb5bd;
    text-align: center;
}

/* Loading animation for waiting states */
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

.progress-status.loading {
    animation: pulse 2s infinite;
}
```

---

## Performance Considerations

### Polling Best Practices

1. **Poll Interval:** 1 second is optimal
   - Too fast (< 500ms): Unnecessary server load
   - Too slow (> 2s): Feels unresponsive

2. **Exponential Backoff:** Consider increasing interval for long tasks
   ```javascript
   let pollCount = 0;
   const getPollInterval = () => {
       if (pollCount < 10) return 1000;      // 1s for first 10 polls
       if (pollCount < 30) return 2000;      // 2s for next 20 polls
       return 3000;                           // 3s after that
   };
   ```

3. **Cleanup:** Always clear intervals on unmount
   ```javascript
   useEffect(() => {
       const interval = setInterval(poll, 1000);
       return () => clearInterval(interval);  // Cleanup!
   }, []);
   ```

### Redis Considerations

- Each `update_state()` call writes ~100-200 bytes to Redis
- 5 progress updates per task = ~500 bytes
- At 100 concurrent analyses = ~50 KB total
- Redis memory impact: **Negligible** ✅

### Network Overhead

- Polling every 1 second for 15 seconds = 15 requests
- Each status check response: ~200-500 bytes
- Total bandwidth per analysis: ~7.5 KB
- Impact on most connections: **Minimal** ✅

---

## Testing Checklist

### Backend Testing

- [ ] Progress updates appear in correct order
- [ ] Each step shows appropriate percentage
- [ ] Task state transitions correctly (PENDING → PROGRESS → SUCCESS)
- [ ] Progress metadata includes all required fields
- [ ] Error cases don't break progress tracking
- [ ] Cache hits don't skip progress updates
- [ ] Multiple concurrent tasks don't interfere

### Frontend Testing

- [ ] Progress bar animates smoothly
- [ ] Status messages update in real-time
- [ ] Completion triggers correct UI state
- [ ] Error states display properly
- [ ] Cleanup on unmount (no memory leaks)
- [ ] Works across different browsers
- [ ] Mobile responsive

### Integration Testing

- [ ] End-to-end flow: submit → progress → complete
- [ ] Handles slow network conditions
- [ ] Recovers from temporary disconnections
- [ ] Multiple analyses can run simultaneously
- [ ] Deep info mode shows correct progress
- [ ] Screenshot inclusion doesn't break progress

---

## Monitoring & Debugging

### Logging Progress Updates

```python
# In tasks.py
logger.info(f"Progress update: {step}/5 - {percent}% - {status}")
```

### Flower Monitoring

- View real-time task progress in Flower dashboard
- URL: `http://localhost:5555`
- Shows task states including custom PROGRESS state
- Monitor worker performance and task throughput

### Redis Inspection

```bash
# View task state in Redis
redis-cli GET celery-task-meta-<task_id>

# Monitor Redis memory usage
redis-cli INFO memory
```

### Browser DevTools

```javascript
// Console logging for debugging
console.log('Progress:', progress);
console.log('Task state:', taskState);

// Network tab: Monitor polling frequency
// Performance tab: Check for memory leaks
```

---

## FAQ

### Q: Will this slow down the analysis?

**A:** No. Progress updates add < 50ms total overhead across all steps. The AI analysis (5-10 seconds) dominates the timeline.

### Q: What if Redis is unavailable?

**A:** Celery's `update_state()` silently fails if Redis is down. The analysis continues normally, just without progress updates.

### Q: Can I skip certain steps?

**A:** Yes, adjust the `current` and `total` values. For example, if browser is already cached, skip step 1 and start from step 2.

### Q: How accurate are time-based estimates?

**A:** They're 70-80% accurate on average. Fast sites finish under 10s, slow sites take 20s+. Real progress (Option 1) is always more accurate.

### Q: Should I use both real and estimated progress?

**A:** Yes! Use estimates initially, then switch to real progress when backend is updated. Provides immediate UX improvement while building toward production solution.

---

## Additional Resources

- [Celery States Documentation](https://docs.celeryq.dev/en/stable/reference/celery.states.html)
- [FastAPI WebSocket Guide](https://fastapi.tiangolo.com/advanced/websockets/)
- [Server-Sent Events (SSE) Specification](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [React Hook Best Practices](https://react.dev/reference/react)
- [Vue Composition API](https://vuejs.org/guide/extras/composition-api-faq.html)

---

## Next Steps

1. **Choose your approach** (Option 1, 2, or 3)
2. **Review code examples** relevant to your frontend stack
3. **Implement backend changes** if using Option 1 or 2
4. **Update frontend** with progress display
5. **Test thoroughly** across browsers and scenarios
6. **Deploy** and gather user feedback
7. **Iterate** based on real-world usage

Good luck! 🚀
