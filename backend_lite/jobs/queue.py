"""
Job Queue Management
====================

Redis Queue (RQ) integration for async jobs.
"""

import os
import logging
from typing import Optional, Dict, Any, Callable
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Redis configuration
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Queue names
QUEUE_DEFAULT = "default"
QUEUE_HIGH = "high"
QUEUE_LOW = "low"

# Try to import RQ
try:
    from redis import Redis
    from rq import Queue, Retry
    from rq.job import Job
    RQ_AVAILABLE = True
except ImportError:
    RQ_AVAILABLE = False
    logger.warning("RQ not installed. Job queue will use synchronous fallback.")


def get_redis_connection():
    """Get Redis connection"""
    if not RQ_AVAILABLE:
        return None
    return Redis.from_url(REDIS_URL)


def get_queue(queue_name: str = QUEUE_DEFAULT) -> Optional['Queue']:
    """Get RQ queue by name"""
    if not RQ_AVAILABLE:
        return None

    conn = get_redis_connection()
    return Queue(queue_name, connection=conn)


def enqueue_job(
    func: Callable,
    *args,
    queue_name: str = QUEUE_DEFAULT,
    job_id: str = None,
    timeout: int = 600,  # 10 minutes default
    retry: int = 3,
    depends_on: str = None,
    at_front: bool = False,
    meta: Dict[str, Any] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Enqueue a job for async processing.

    Args:
        func: Function to execute
        *args: Positional arguments for function
        queue_name: Queue to use (default/high/low)
        job_id: Optional custom job ID
        timeout: Job timeout in seconds
        retry: Number of retries on failure
        depends_on: Job ID to wait for
        at_front: Push to front of queue
        meta: Custom metadata for job
        **kwargs: Keyword arguments for function

    Returns:
        Dict with job_id and status
    """
    def _run_sync(reason: str) -> Dict[str, Any]:
        logger.warning(f"Running job synchronously ({reason})")
        try:
            result = func(*args, **kwargs)
            return {
                "job_id": job_id or "sync",
                "status": "done",
                "result": result
            }
        except Exception as e:
            return {
                "job_id": job_id or "sync",
                "status": "failed",
                "error": str(e)
            }

    if not RQ_AVAILABLE:
        return _run_sync("RQ not available")

    queue = get_queue(queue_name)

    # Build retry policy
    retry_policy = Retry(max=retry, interval=[10, 30, 60]) if retry > 0 else None

    # Get dependency
    dependency = None
    if depends_on:
        try:
            dependency = Job.fetch(depends_on, connection=get_redis_connection())
        except:
            pass

    # Enqueue job (fallback to sync if Redis is unreachable)
    try:
        job = queue.enqueue(
            func,
            *args,
            job_id=job_id,
            job_timeout=timeout,
            retry=retry_policy,
            depends_on=dependency,
            at_front=at_front,
            meta=meta or {},
            **kwargs
        )
    except Exception as e:
        return _run_sync(f"RQ enqueue failed: {e}")

    return {
        "job_id": job.id,
        "status": job.get_status(),
        "queue": queue_name,
        "enqueued_at": datetime.utcnow().isoformat()
    }


def get_job_status(job_id: str) -> Dict[str, Any]:
    """
    Get job status and result.

    Args:
        job_id: Job ID

    Returns:
        Dict with status, progress, result, error
    """
    if not RQ_AVAILABLE:
        return {
            "job_id": job_id,
            "status": "unknown",
            "error": "RQ not available"
        }

    try:
        job = Job.fetch(job_id, connection=get_redis_connection())

        result = {
            "job_id": job_id,
            "status": job.get_status(),
            "meta": job.meta,
            "enqueued_at": job.enqueued_at.isoformat() if job.enqueued_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "ended_at": job.ended_at.isoformat() if job.ended_at else None,
        }

        if job.is_finished:
            result["result"] = job.result
        elif job.is_failed:
            result["error"] = str(job.exc_info) if job.exc_info else "Unknown error"
            result["error_message"] = job.meta.get("error_message", "")

        # Get progress from meta
        result["progress"] = job.meta.get("progress", 0)

        return result

    except Exception as e:
        return {
            "job_id": job_id,
            "status": "not_found",
            "error": str(e)
        }


def cancel_job(job_id: str) -> bool:
    """
    Cancel a pending or running job.

    Args:
        job_id: Job ID

    Returns:
        True if cancelled successfully
    """
    if not RQ_AVAILABLE:
        return False

    try:
        job = Job.fetch(job_id, connection=get_redis_connection())
        job.cancel()
        return True
    except:
        return False


def get_queue_stats() -> Dict[str, Any]:
    """Get statistics for all queues"""
    if not RQ_AVAILABLE:
        return {"available": False}

    conn = get_redis_connection()

    stats = {"available": True, "queues": {}}

    for queue_name in [QUEUE_DEFAULT, QUEUE_HIGH, QUEUE_LOW]:
        queue = Queue(queue_name, connection=conn)
        stats["queues"][queue_name] = {
            "length": len(queue),
            "failed": queue.failed_job_registry.count,
            "scheduled": queue.scheduled_job_registry.count,
        }

    return stats


def retry_failed_jobs(queue_name: str = QUEUE_DEFAULT, max_jobs: int = 100) -> int:
    """Retry failed jobs in a queue"""
    if not RQ_AVAILABLE:
        return 0

    queue = get_queue(queue_name)
    failed_registry = queue.failed_job_registry

    count = 0
    for job_id in failed_registry.get_job_ids()[:max_jobs]:
        try:
            failed_registry.requeue(job_id)
            count += 1
        except:
            pass

    return count


def clear_queue(queue_name: str = QUEUE_DEFAULT) -> int:
    """Clear all jobs from a queue"""
    if not RQ_AVAILABLE:
        return 0

    queue = get_queue(queue_name)
    count = len(queue)
    queue.empty()
    return count
