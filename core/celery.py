"""
Celery application configuration for CRO Analyzer
Handles background task processing with Redis as broker
"""

from celery import Celery
from kombu import Queue

from config import settings

# Create Celery application
celery_app = Celery(
    "cro_analyzer",
    broker=settings.celery_broker,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["tasks.analysis"],  # Auto-discover tasks from tasks/analysis.py
)

# Celery Configuration
celery_app.conf.update(
    # Task Settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task Execution
    task_acks_late=True,  # Acknowledge task after completion (ensures no lost tasks)
    task_reject_on_worker_lost=True,  # Re-queue if worker crashes
    task_track_started=True,  # Track when tasks start (for monitoring)
    # Task Time Limits
    task_time_limit=settings.TASK_TIME_LIMIT,  # Hard limit (kills task)
    task_soft_time_limit=settings.TASK_SOFT_TIME_LIMIT,  # Soft limit (raises exception)
    # Result Backend Settings
    result_expires=settings.CELERY_RESULT_EXPIRES,  # Results expire after configured time
    result_extended=True,  # Store additional metadata
    # Worker Settings
    worker_prefetch_multiplier=settings.WORKER_PREFETCH_MULTIPLIER,  # Fetch tasks at a time
    worker_max_tasks_per_child=settings.WORKER_MAX_TASKS_PER_CHILD,  # Restart worker after N tasks
    worker_disable_rate_limits=False,
    # Retry Policy
    task_default_retry_delay=settings.TASK_DEFAULT_RETRY_DELAY,
    task_max_retries=settings.TASK_MAX_RETRIES,
    # Queue Configuration
    task_default_queue="default",
    task_queues=(
        Queue("default", routing_key="task.default"),
        Queue("priority", routing_key="task.priority"),  # For urgent tasks
    ),
    # Monitoring
    worker_send_task_events=True,  # Enable task events (for Flower monitoring)
    task_send_sent_event=True,
    # Optimization
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
    # Task result compression (saves Redis memory)
    result_compression="gzip",
    # Beat scheduler (if needed for periodic tasks in future)
    beat_schedule={
        # Example periodic task (disabled by default)
        # "cleanup-old-results": {
        #     "task": "tasks.cleanup_old_results",
        #     "schedule": 3600.0,  # Every hour
        # },
    },
)

# Task Routing
celery_app.conf.task_routes = {
    "tasks.analyze_website": {"queue": "default"},
    "tasks.analyze_website_priority": {"queue": "priority"},
}


# Celery Signals for Logging and Monitoring
from celery.signals import (
    task_prerun,
    task_postrun,
    task_failure,
    task_retry,
    worker_ready,
    worker_shutdown,
)
import logging

logger = logging.getLogger(__name__)


@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """Called when worker starts"""
    logger.info("🚀 Celery worker is ready and waiting for tasks")


@worker_shutdown.connect
def worker_shutdown_handler(sender=None, **kwargs):
    """Called when worker shuts down"""
    logger.info("🛑 Celery worker is shutting down")


@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, **kwargs):
    """Called before task execution"""
    logger.info(f"⏳ Starting task: {task.name} [ID: {task_id}]")


@task_postrun.connect
def task_postrun_handler(
    sender=None, task_id=None, task=None, retval=None, state=None, **kwargs
):
    """Called after task execution"""
    logger.info(f"✅ Completed task: {task.name} [ID: {task_id}] [State: {state}]")


@task_failure.connect
def task_failure_handler(
    sender=None, task_id=None, exception=None, traceback=None, **kwargs
):
    """Called when task fails"""
    logger.error(
        f"❌ Task failed: {sender.name} [ID: {task_id}] [Error: {str(exception)}]"
    )


@task_retry.connect
def task_retry_handler(sender=None, task_id=None, reason=None, **kwargs):
    """Called when task is retried"""
    logger.warning(
        f"🔄 Retrying task: {sender.name} [ID: {task_id}] [Reason: {reason}]"
    )


if __name__ == "__main__":
    # Start worker with: celery -A celery_app worker --loglevel=info
    celery_app.start()
