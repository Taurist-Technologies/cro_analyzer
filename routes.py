from typing import Union
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from models import AnalysisRequest, AnalysisResponse, DeepAnalysisResponse
from datetime import datetime
import asyncio
import traceback
import anthropic
import os
import re

# Create router
router = APIRouter()


@router.get("/")
async def root():
    return {
        "service": "CRO Analyzer",
        "status": "running",
        "endpoints": {"analyze": "/analyze (POST)"},
    }


@router.post("/analyze", response_model=Union[AnalysisResponse, DeepAnalysisResponse])
async def analyze_website(request: AnalysisRequest):
    """
    Analyzes a website for CRO issues and returns actionable recommendations.

    By default, returns 2-3 key points. Set deep_info=true for comprehensive analysis with:
    - Total issues identified
    - Top 5 issues with detailed breakdown
    - Executive summary with strategic guidance
    - CRO analysis score (0-100)
    - Site performance score (0-100)
    - Conversion rate increase potential estimate

    Screenshots are NOT included in the response by default. Set include_screenshots=true to include them.
    """
    from utils.screenshot_analyzer import capture_screenshot_and_analyze

    try:
        result = await capture_screenshot_and_analyze(
            str(request.url), request.include_screenshots, request.deep_info
        )
        return result
    except asyncio.TimeoutError as e:
        print(f"ERROR: Page navigation timeout for {request.url}: {str(e)}")
        traceback.print_exc()
        raise HTTPException(
            status_code=504,
            detail="Page load timeout exceeded 60 seconds. The target website may be slow or unresponsive.",
        )
    except anthropic.APIError as e:
        print(f"ERROR: Anthropic API failure for {request.url}: {str(e)}")
        traceback.print_exc()
        raise HTTPException(
            status_code=502, detail=f"AI analysis service failed: {str(e)}"
        )
    except ValueError as e:
        error_msg = str(e)
        print(
            f"ERROR: JSON parsing or validation failed for {request.url}: {error_msg}"
        )
        traceback.print_exc()
        raise HTTPException(
            status_code=422, detail=f"Analysis parsing failed: {error_msg}"
        )
    except RuntimeError as e:
        error_msg = str(e)
        print(f"ERROR: Runtime error for {request.url}: {error_msg}")
        traceback.print_exc()
        if "browser" in error_msg.lower():
            raise HTTPException(
                status_code=503, detail=f"Browser service unavailable: {error_msg}"
            )
        raise HTTPException(status_code=500, detail=f"Service error: {error_msg}")
    except Exception as e:
        error_msg = str(e)
        print(f"ERROR: Unexpected failure for {request.url}: {error_msg}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {error_msg}")


@router.post("/analyze/async")
async def analyze_website_async(request: AnalysisRequest):
    """
    Submit a website analysis task for background processing.
    Returns immediately with a task_id for status polling.

    This endpoint is designed for high-concurrency scenarios where
    you don't want to wait for the analysis to complete.

    Returns:
        {
            "task_id": "abc-123-def",
            "status": "PENDING",
            "message": "Analysis task submitted successfully"
        }
    """
    try:
        from tasks import analyze_website as analyze_task

        # Submit task to Celery
        task = analyze_task.delay(
            str(request.url), request.include_screenshots, request.deep_info
        )

        return {
            "task_id": task.id,
            "status": "PENDING",
            "message": "Analysis task submitted successfully",
            "poll_url": f"/analyze/status/{task.id}",
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to submit analysis task: {str(e)}"
        )


@router.get("/analyze/status/{task_id}")
async def get_task_status(task_id: str):
    """
    Check the status of a background analysis task.

    Returns:
        - PENDING: Task is waiting in queue
        - STARTED: Task is being processed
        - PROGRESS: Task is in progress (includes progress info: percent, status, current step)
        - RETRYING: Task is retrying after timeout (includes attempt number and reason)
        - SUCCESS: Task completed successfully (includes result)
        - FAILURE: Task failed (includes error details)
        - RETRY: Task is being retried (Celery internal state)
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
            response["progress"] = (
                task.info
            )  # Contains: current, total, percent, status, url

        elif task.state == "SUCCESS":
            response["message"] = "Task completed successfully"
            response["result"] = task.result

        elif task.state == "FAILURE":
            response["message"] = "Task failed"
            response["error"] = str(task.info)

        elif task.state == "RETRY":
            response["message"] = "Task is being retried"
            response["retry_info"] = str(task.info)

        elif task.state == "RETRYING":
            response["message"] = "Task is retrying after timeout"
            if isinstance(task.info, dict):
                response["retry_info"] = {
                    "attempt": task.info.get("attempt", "unknown"),
                    "max_attempts": task.info.get("max_attempts", 3),
                    "reason": task.info.get("reason", "Timeout"),
                    "url": task.info.get("url", ""),
                    "message": task.info.get("message", "Retrying..."),
                }
            else:
                response["retry_info"] = str(task.info)

        else:
            response["message"] = f"Unknown state: {task.state}"

        return response

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get task status: {str(e)}"
        )


@router.get("/analyze/result/{task_id}")
async def get_task_result(task_id: str):
    """
    Get the result of a completed analysis task.
    Returns 404 if task doesn't exist or isn't complete yet.
    """
    try:
        from celery.result import AsyncResult

        task = AsyncResult(task_id)

        if task.state == "SUCCESS":
            return {
                "task_id": task_id,
                "status": "SUCCESS",
                "result": task.result,
            }
        elif task.state == "PENDING":
            raise HTTPException(
                status_code=202,
                detail="Task is still pending. Please check status endpoint.",
            )
        elif task.state == "STARTED":
            raise HTTPException(
                status_code=202,
                detail="Task is being processed. Please check status endpoint.",
            )
        elif task.state == "FAILURE":
            raise HTTPException(status_code=500, detail=f"Task failed: {task.info}")
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Task not found or in unknown state: {task.state}",
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get task result: {str(e)}"
        )


@router.post("/generate-pdf/{task_id}")
async def generate_pdf_report(task_id: str):
    """
    Generate a PDF report for a completed analysis task.

    Args:
        task_id: The Celery task ID from /analyze/async

    Returns:
        StreamingResponse with PDF file for download
    """
    from utils.pdf_generator import generate_pdf, register_fonts

    try:
        from celery.result import AsyncResult

        # Get task result from Celery
        task = AsyncResult(task_id)

        # Check if task exists and is complete
        if task.state == "PENDING":
            raise HTTPException(
                status_code=404, detail="Task not found. Please check the task_id."
            )

        if task.state == "STARTED":
            raise HTTPException(
                status_code=202,
                detail="Analysis is still in progress. Please wait for completion before generating PDF.",
            )

        if task.state == "FAILURE":
            raise HTTPException(
                status_code=400,
                detail=f"Analysis failed: {str(task.info)}. Cannot generate PDF.",
            )

        if task.state != "SUCCESS":
            raise HTTPException(
                status_code=400,
                detail=f"Task is in unexpected state: {task.state}. Cannot generate PDF.",
            )

        # Get the analysis result
        analysis_data = task.result

        if not analysis_data or not isinstance(analysis_data, dict):
            raise HTTPException(
                status_code=500,
                detail="Invalid analysis data format. Cannot generate PDF.",
            )

        # Register fonts for PDF generation
        register_fonts()

        # Generate PDF in memory
        pdf_buffer = generate_pdf(analysis_data, output_path=None)

        if not pdf_buffer:
            raise HTTPException(
                status_code=500, detail="PDF generation failed unexpectedly."
            )

        # Create a safe filename from the URL
        url = analysis_data.get("url", "analysis")
        # Remove protocol and sanitize
        safe_url = re.sub(
            r"[^\w\-]", "-", url.replace("https://", "").replace("http://", "")
        )
        safe_url = safe_url[:50]  # Limit length

        # Get timestamp
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # Create filename
        filename = f"cro-analysis-{safe_url}-{timestamp}.pdf"

        # Return as streaming response
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"PDF generation error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(e)}")


@router.get("/health")
async def health_check():
    return {"status": "healthy"}


@router.get("/status/detailed")
async def detailed_status_check():
    """
    Enhanced status check with Redis, Celery, and browser pool health.

    Returns comprehensive system health information for monitoring.
    """
    status_info = {
        "api": "healthy",
        "redis": "unknown",
        "celery": "unknown",
        "browser_pool": "unknown",
        "anthropic_api": "configured" if os.getenv("ANTHROPIC_API_KEY") else "missing",
    }

    # Check Redis connection
    try:
        from redis_client import get_redis_client

        redis_client = get_redis_client()
        if redis_client.ping():
            status_info["redis"] = "connected"
            status_info["redis_stats"] = redis_client.get_stats()
        else:
            status_info["redis"] = "disconnected"
    except Exception as e:
        status_info["redis"] = f"error: {str(e)}"

    # Check Celery workers
    try:
        from celery_app import celery_app

        inspect = celery_app.control.inspect()
        active_workers = inspect.active()

        if active_workers:
            status_info["celery"] = "workers_active"
            status_info["celery_workers"] = list(active_workers.keys())
        else:
            status_info["celery"] = "no_workers"
    except Exception as e:
        status_info["celery"] = f"error: {str(e)}"

    # Check browser pool (if initialized)
    try:
        from browser_pool import _browser_pool

        if _browser_pool and _browser_pool._initialized:
            pool_health = await _browser_pool.health_check()
            status_info["browser_pool"] = pool_health
        else:
            status_info["browser_pool"] = "not_initialized"
    except Exception as e:
        status_info["browser_pool"] = f"error: {str(e)}"

    # Determine overall health
    critical_components = [
        status_info["redis"],
        status_info["anthropic_api"],
    ]

    if any(
        "error" in str(c) or "missing" in str(c) or "disconnected" in str(c)
        for c in critical_components
    ):
        status_info["overall_status"] = "degraded"
    else:
        status_info["overall_status"] = "healthy"

    return status_info


@router.delete("/cache/task/{task_id}")
async def clear_task_cache(task_id: str):
    """
    Clear Celery task result from Redis cache by task ID.

    This removes the task result from the Celery result backend (Redis DB 1).
    Useful for clearing stale or stuck task results.

    Args:
        task_id: The Celery task ID (UUID format)

    Returns:
        JSON with cleared status and task details
    """
    try:
        from celery_app import celery_app

        # Get the result backend (Redis DB 1)
        backend = celery_app.backend

        # Delete the task result using Celery's backend
        # This handles the correct key format: celery-task-meta-{task_id}
        backend.forget(task_id)

        return {
            "cleared": True,
            "task_id": task_id,
            "message": f"Task result removed from cache",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to clear task cache: {str(e)}"
        )


@router.delete("/cache/analysis/{url:path}")
async def clear_analysis_cache(url: str):
    """
    Clear cached analysis result for a specific URL.

    This removes the 24-hour cached analysis from Redis DB 0.
    Useful for forcing a fresh analysis of a previously analyzed site.

    Args:
        url: The website URL (should be URL-encoded if it contains special characters)

    Returns:
        JSON with cleared status and URL details
    """
    try:
        from redis_client import get_redis_client

        redis_client = get_redis_client()
        cleared = redis_client.clear_analysis_cache(url)

        return {
            "cleared": cleared,
            "url": url,
            "message": "Analysis cache removed" if cleared else "Cache entry not found",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to clear analysis cache: {str(e)}"
        )
