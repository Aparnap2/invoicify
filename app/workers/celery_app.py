"""
Celery application configuration for background task processing.
"""

import logging
import os

from celery import Celery
from kombu import Queue

from app.core.config import settings

logger = logging.getLogger(__name__)

# Create Celery app
celery_app = Celery(
    "ap_intake",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.invoice_tasks",
        "app.workers.email_tasks",
        "app.workers.maintenance_tasks",
        "app.workers.benchmark_tasks",
    ]
)

# Celery configuration
celery_app.conf.update(
    # Task configuration
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_compression="gzip",  # Compress large task messages
    result_compression="gzip",
    task_inherit_parent_priority=True,

    # Worker configuration
    worker_concurrency=settings.WORKER_CONCURRENCY,
    worker_prefetch_multiplier=settings.WORKER_PREFETCH_MULTIPLIER,
    task_soft_time_limit=settings.WORKER_TASK_SOFT_TIME_LIMIT,
    task_time_limit=settings.WORKER_TASK_TIME_LIMIT,
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks
    worker_disable_rate_limits=False,
    worker_pool_restarts=True,

    # Task routing
    task_routes={
        "app.workers.invoice_tasks.process_invoice_task": {"queue": "invoice_processing"},
        "app.workers.invoice_tasks.validate_invoice_task": {"queue": "validation"},
        "app.workers.invoice_tasks.export_invoice_task": {"queue": "export"},
        "app.workers.email_tasks.process_email_task": {"queue": "email_processing"},
        "app.workers.dlq_handlers.*": {"queue": "dlq_processing"},
        "app.workers.redrive_tasks.*": {"queue": "dlq_redrive"},
    },

    # Queue configuration
    task_queues=(
        Queue("invoice_processing", routing_key="invoice_processing"),
        Queue("validation", routing_key="validation"),
        Queue("export", routing_key="export"),
        Queue("email_processing", routing_key="email_processing"),
        Queue("dlq_processing", routing_key="dlq_processing"),
        Queue("dlq_redrive", routing_key="dlq_redrive"),
        Queue("celery", routing_key="celery"),  # Default queue
    ),

    # Result backend configuration
    result_expires=3600,  # 1 hour
    result_backend_transport_options={
        "master_name": "mymaster",
        "socket_keepalive": True,
        "socket_keepalive_options": {},
        "socket_connect_timeout": 30,
    },

    # Beat scheduler configuration
    beat_schedule={
        "cleanup-old-exports": {
            "task": "app.workers.maintenance_tasks.cleanup_old_exports",
            "schedule": 3600.0,  # Every hour
        },
        "health-check": {
            "task": "app.workers.maintenance_tasks.health_check",
            "schedule": 300.0,  # Every 5 minutes
        },
        "cleanup-failed-tasks": {
            "task": "app.workers.maintenance_tasks.cleanup_failed_tasks",
            "schedule": 86400.0,  # Every day
        },
        "monitor-performance": {
            "task": "app.workers.maintenance_tasks.monitor_worker_performance",
            "schedule": 1800.0,  # Every 30 minutes
        },
        "cleanup-temp-files": {
            "task": "app.workers.maintenance_tasks.cleanup_temp_files",
            "schedule": 21600.0,  # Every 6 hours
        },
        "generate-report": {
            "task": "app.workers.maintenance_tasks.generate_system_report",
            "schedule": 43200.0,  # Every 12 hours
        },
    },

    # Error handling
    task_reject_on_worker_lost=True,
    task_acks_late=True,

    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# Configure logging for Celery
if not os.environ.get("FORKED_BY_MULTIPROCESSING"):
    import logging
    from logging.handlers import RotatingFileHandler

    # Configure file handler for Celery logs
    file_handler = RotatingFileHandler(
        "logs/celery.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    )

    # Get Celery logger and add handler
    celery_logger = logging.getLogger("celery")
    celery_logger.addHandler(file_handler)
    celery_logger.setLevel(logging.INFO)

# Configure signals for task monitoring
from celery.signals import task_prerun, task_postrun, task_failure, task_success

# Import DLQ error handlers to register signals
from app.workers.dlq_handlers import error_handler


@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **kwds):
    """Handle task pre-run signal."""
    logger.info(f"Task {sender.name} started (ID: {task_id})")


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **kwds):
    """Handle task post-run signal."""
    logger.info(f"Task {sender.name} completed (ID: {task_id}, state: {state})")


@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, traceback=None, einfo=None, **kwds):
    """Handle task failure signal."""
    logger.error(f"Task {sender.name} failed (ID: {task_id}): {exception}")


@task_success.connect
def task_success_handler(sender=None, result=None, **kwargs):
    """Handle task success signal."""
    logger.info(f"Task {sender.name} succeeded")


if __name__ == "__main__":
    celery_app.start()