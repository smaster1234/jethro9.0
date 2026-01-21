"""
RQ Worker
=========

Worker process for executing async jobs.
"""

import os
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

# Redis configuration
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def start_worker(
    queues: list = None,
    burst: bool = False,
    logging_level: str = "INFO"
):
    """
    Start an RQ worker.

    Args:
        queues: List of queue names to listen to
        burst: Run in burst mode (exit when queues are empty)
        logging_level: Logging level
    """
    try:
        from redis import Redis
        from rq import Worker
    except ImportError:
        logger.error("RQ not installed. Install with: pip install rq redis")
        return

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, logging_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Default queues
    if queues is None:
        queues = ['high', 'default', 'low']

    # Connect to Redis
    conn = Redis.from_url(REDIS_URL)

    # Create worker
    worker = Worker(
        queues,
        connection=conn,
        worker_ttl=420,  # 7 minutes
        job_monitoring_interval=5,
    )

    logger.info(f"Starting worker on queues: {queues}")

    # Start worker
    worker.work(burst=burst)


def run_worker_cli():
    """CLI entry point for worker"""
    import argparse

    parser = argparse.ArgumentParser(description="RQ Worker for JETHRO4")
    parser.add_argument(
        "--queues", "-q",
        nargs="+",
        default=["high", "default", "low"],
        help="Queues to listen to"
    )
    parser.add_argument(
        "--burst", "-b",
        action="store_true",
        help="Run in burst mode"
    )
    parser.add_argument(
        "--log-level", "-l",
        default="INFO",
        help="Logging level"
    )

    args = parser.parse_args()
    start_worker(
        queues=args.queues,
        burst=args.burst,
        logging_level=args.log_level
    )


if __name__ == "__main__":
    run_worker_cli()
