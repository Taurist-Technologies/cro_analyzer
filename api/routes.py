"""
FastAPI routes for CRO Analyzer — PDP-focused analysis API.

Endpoints:
- POST /analyze            sync analysis (blocks; dev/low-traffic use)
- POST /analyze/async      submit background task (chat integration path)
- GET  /analyze/status/:id poll task state
- GET  /analyze/stream/:id SSE stream of task progress (for live chat UX)
- GET  /analyze/result/:id fetch completed result
- GET  /analyze/screenshots/:id fetch stored screenshots for a task
- POST /generate-pdf/:id   PDF report for a completed task
- GET  /health, /status/detailed, cache management
"""

import asyncio
import json
import logging
import re
import traceback
from datetime import datetime

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from config import settings
from api.models import AnalysisRequest, PDPAnalysisResponse
from api.security import enforce_rate_limit, require_api_key
from utils.net import normalize_url, validate_public_url, UnsafeURLError

logger = logging.getLogger(__name__)

router = APIRouter()

ANALYZE_DEPS = [Depends(require_api_key), Depends(enforce_rate_limit)]


@router.get("/")
async def root():
    return {
        "service": "CRO Analyzer",
        "focus": "Product detail page (PDP) analysis",
        "status": "running",
        "endpoints": {
            "analyze_sync": "POST /analyze",
            "analyze_async": "POST /analyze/async",
            "status": "GET /analyze/status/{task_id}",
            "stream": "GET /analyze/stream/{task_id}",
            "result": "GET /analyze/result/{task_id}",
        },
    }


@router.get("/health")
async def health_check():
    return {"status": "healthy"}


def _validated_url(request: AnalysisRequest) -> str:
    url = normalize_url(str(request.url))
    try:
        validate_public_url(url)
    except UnsafeURLError as e:
        raise HTTPException(status_code=400, detail=f"URL rejected: {e}")
    return url


# ---------------------------------------------------------------------------
# Sync analysis
# ---------------------------------------------------------------------------

@router.post("/analyze", response_model=PDPAnalysisResponse, dependencies=ANALYZE_DEPS)
async def analyze_website(request: AnalysisRequest):
    """Blocking PDP analysis. Prefer /analyze/async for production traffic."""
    from analyzer.pdp.analysis import analyze_url_standalone

    url = _validated_url(request)
    try:
        result = await analyze_url_standalone(url, request.include_screenshots)
        result.pop("_screenshots", None)
        return result
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Analysis exceeded {settings.ANALYSIS_TIMEOUT}s. The site may be slow or blocking automation.",
        )
    except anthropic.APIError as e:
        logger.error(f"Anthropic API failure for {url}: {e}")
        raise HTTPException(status_code=502, detail=f"AI analysis service failed: {e}")
    except Exception as e:
        logger.error(f"Analysis failed for {url}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


# ---------------------------------------------------------------------------
# Async analysis (chat integration path)
# ---------------------------------------------------------------------------

@router.post("/analyze/async", dependencies=ANALYZE_DEPS)
async def analyze_website_async(request: AnalysisRequest):
    """Submit a PDP analysis task; returns immediately with a task_id."""
    url = _validated_url(request)
    try:
        from tasks.analysis import analyze_website as analyze_task

        task = analyze_task.delay(url, request.include_screenshots)
        return {
            "task_id": task.id,
            "status": "PENDING",
            "message": "Analysis task submitted",
            "poll_url": f"/analyze/status/{task.id}",
            "stream_url": f"/analyze/stream/{task.id}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit analysis task: {e}")


def _task_state(task_id: str) -> dict:
    from celery.result import AsyncResult

    task = AsyncResult(task_id)
    response = {"task_id": task_id, "status": task.state}

    if task.state == "PROGRESS" and isinstance(task.info, dict):
        response["progress"] = task.info
    elif task.state == "SUCCESS":
        response["result"] = task.result
    elif task.state == "FAILURE":
        response["error"] = str(task.info)
    elif task.state == "RETRY":
        response["message"] = "First attempt timed out; retrying"
    return response


@router.get("/analyze/status/{task_id}")
async def get_task_status(task_id: str):
    """Poll task status. PROGRESS states include percent + human status text."""
    try:
        response = _task_state(task_id)
        if response["status"] == "PENDING":
            from core.celery import celery_app

            if not celery_app.backend.client.exists(f"celery-task-meta-{task_id}"):
                response["message"] = "Task queued or unknown (results are retained for 72 hours)"
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get task status: {e}")


@router.get("/analyze/stream/{task_id}")
async def stream_task_progress(task_id: str):
    """
    Server-Sent Events stream of task progress — lets the chat widget show
    live status ('Loading your page...', 'Testing add-to-cart...') without
    polling. Emits a final 'result'/'error' event and closes.
    """

    async def event_stream():
        deadline = asyncio.get_event_loop().time() + settings.TASK_TIME_LIMIT + 60
        last_payload = None
        while asyncio.get_event_loop().time() < deadline:
            state = _task_state(task_id)
            status = state["status"]

            if status == "SUCCESS":
                yield f"event: result\ndata: {json.dumps(state)}\n\n"
                return
            if status == "FAILURE":
                yield f"event: error\ndata: {json.dumps(state)}\n\n"
                return

            payload = json.dumps(state)
            if payload != last_payload:
                last_payload = payload
                yield f"event: progress\ndata: {payload}\n\n"
            await asyncio.sleep(1.0)

        yield f"event: error\ndata: {json.dumps({'task_id': task_id, 'status': 'TIMEOUT'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/analyze/result/{task_id}")
async def get_task_result(task_id: str):
    """Fetch the completed result. 202 while processing, 404 if unknown."""
    try:
        from celery.result import AsyncResult

        task = AsyncResult(task_id)
        if task.state == "SUCCESS":
            return {"task_id": task_id, "status": "SUCCESS", "result": task.result}
        if task.state in ("PENDING", "STARTED", "PROGRESS", "RETRY"):
            raise HTTPException(status_code=202, detail="Task is still processing")
        if task.state == "FAILURE":
            raise HTTPException(status_code=500, detail=f"Task failed: {task.info}")
        raise HTTPException(status_code=404, detail=f"Task in unknown state: {task.state}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get task result: {e}")


@router.get("/analyze/screenshots/{task_id}", dependencies=[Depends(require_api_key)])
async def get_task_screenshots(task_id: str):
    """Screenshots for a completed task (retained 1 hour, stored off-result)."""
    try:
        from core.cache import get_redis_client

        shots = get_redis_client().get(f"screens:{task_id}")
        if not shots:
            raise HTTPException(
                status_code=404,
                detail="Screenshots not found (they are retained for 1 hour after analysis)",
            )
        return {"task_id": task_id, "screenshots": shots}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get screenshots: {e}")


# ---------------------------------------------------------------------------
# PDF report
# ---------------------------------------------------------------------------

@router.post("/generate-pdf/{task_id}")
async def generate_pdf_report(task_id: str):
    """Generate a PDF report for a completed analysis task."""
    from utils.reporting.pdf import generate_pdf, register_fonts

    try:
        from celery.result import AsyncResult

        task = AsyncResult(task_id)
        if task.state in ("PENDING",):
            raise HTTPException(status_code=404, detail="Task not found")
        if task.state in ("STARTED", "PROGRESS", "RETRY"):
            raise HTTPException(status_code=202, detail="Analysis still in progress")
        if task.state == "FAILURE":
            raise HTTPException(status_code=400, detail=f"Analysis failed: {task.info}")

        analysis_data = task.result
        if not isinstance(analysis_data, dict):
            raise HTTPException(status_code=500, detail="Invalid analysis data format")
        if analysis_data.get("status") == "not_product_page":
            raise HTTPException(status_code=400, detail="No report available: URL was not a product page")

        register_fonts()
        pdf_buffer = generate_pdf(analysis_data, output_path=None)
        if not pdf_buffer:
            raise HTTPException(status_code=500, detail="PDF generation failed")

        url = analysis_data.get("url", "analysis")
        safe_url = re.sub(r"[^\w\-]", "-", url.replace("https://", "").replace("http://", ""))[:50]
        filename = f"pdp-analysis-{safe_url}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf"

        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF generation error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {e}")


# ---------------------------------------------------------------------------
# Monitoring & cache management
# ---------------------------------------------------------------------------

@router.get("/status/detailed")
async def detailed_status_check():
    """System health: Redis, Celery workers, browser runtime, API key presence."""
    status_info = {
        "api": "healthy",
        "redis": "unknown",
        "celery": "unknown",
        "anthropic_api": "configured" if settings.ANTHROPIC_API_KEY else "missing",
        "auth_enabled": bool(settings.API_AUTH_KEY),
        "rate_limit_per_minute": settings.RATE_LIMIT_PER_MINUTE,
    }

    try:
        from core.cache import get_redis_client

        redis_client = get_redis_client()
        if redis_client.ping():
            status_info["redis"] = "connected"
            status_info["redis_stats"] = redis_client.get_stats()
        else:
            status_info["redis"] = "disconnected"
    except Exception as e:
        status_info["redis"] = f"error: {e}"

    try:
        from core.celery import celery_app

        active = celery_app.control.inspect(timeout=2).active()
        status_info["celery"] = "workers_active" if active else "no_workers"
        if active:
            status_info["celery_workers"] = list(active.keys())
    except Exception as e:
        status_info["celery"] = f"error: {e}"

    try:
        from core.browser import browser_health

        status_info["browser"] = browser_health()
    except Exception as e:
        status_info["browser"] = f"error: {e}"

    critical = [status_info["redis"], status_info["anthropic_api"]]
    status_info["overall_status"] = (
        "degraded"
        if any(("error" in str(c) or "missing" in str(c) or "disconnected" in str(c)) for c in critical)
        else "healthy"
    )
    return status_info


@router.delete("/cache/task/{task_id}", dependencies=[Depends(require_api_key)])
async def clear_task_cache(task_id: str):
    """Remove a task result from the Celery result backend."""
    try:
        from core.celery import celery_app

        celery_app.backend.forget(task_id)
        return {"cleared": True, "task_id": task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear task cache: {e}")


@router.delete("/cache/analysis/{url:path}", dependencies=[Depends(require_api_key)])
async def clear_analysis_cache(url: str):
    """Clear the cached analysis for a URL (accepts raw or normalized form)."""
    try:
        from core.cache import get_redis_client

        redis_client = get_redis_client()
        cleared = redis_client.clear_analysis_cache(normalize_url(url)) or redis_client.clear_analysis_cache(url)
        return {"cleared": cleared, "url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear analysis cache: {e}")
