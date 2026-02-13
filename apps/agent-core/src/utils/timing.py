import time
import structlog
from contextlib import asynccontextmanager

logger = structlog.get_logger()

@asynccontextmanager
async def timed(operation: str, trace_id: str):
    """Context manager to measure operation timing"""
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "operation_timed",
            operation=operation,
            trace_id=trace_id,
            duration_ms=round(duration_ms, 2),
        )
