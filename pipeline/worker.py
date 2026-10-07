import multiprocessing
import time
import logging
from typing import Callable, Any, Dict

logger = logging.getLogger(__name__)

def _worker_wrapper(func: Callable, queue: multiprocessing.Queue, args: tuple, kwargs: dict):
    """Wrapper to execute a function in a subprocess and return the result via a Queue."""
    try:
        result = func(*args, **kwargs)
        queue.put({"status": "success", "data": result})
    except Exception as e:
        queue.put({"status": "error", "error": str(e), "type": type(e).__name__})

def run_with_timeout(func: Callable, timeout_seconds: int, *args, **kwargs) -> Any:
    """
    Executes a function in a separate, killable process.
    Enforces a strict wall-clock timeout to prevent hanging on corrupt files.
    """
    queue = multiprocessing.Queue()
    process = multiprocessing.Process(
        target=_worker_wrapper, 
        args=(func, queue, args, kwargs)
    )
    
    logger.info(f"Starting killable worker process (timeout={timeout_seconds}s)")
    process.start()
    process.join(timeout_seconds)
    
    if process.is_alive():
        logger.error(f"Worker exceeded timeout of {timeout_seconds}s. Terminating.")
        process.terminate()
        process.join()
        raise TimeoutError(f"Task exceeded hard timeout of {timeout_seconds} seconds")
        
    if not queue.empty():
        result = queue.get()
        if result["status"] == "error":
            raise RuntimeError(f"Worker failed with {result['type']}: {result['error']}")
        return result["data"]
        
    raise RuntimeError("Worker process terminated unexpectedly without returning data.")
