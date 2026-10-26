"""
PowerTrader AI+ Async Patterns
Implements async/await patterns for API calls, I/O operations, and concurrent processing
"""

import asyncio
import aiohttp
import aiofiles
import aiodns
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps
from typing import Any, Dict, List, Optional, Callable, Union, Awaitable
import time
import json
import threading
import queue
from dataclasses import dataclass
from datetime import datetime, timedelta
import weakref


@dataclass
class RequestConfig:
    """Configuration for HTTP requests."""

    timeout: float = 30.0
    retries: int = 3
    backoff_factor: float = 1.0
    headers: Optional[Dict[str, str]] = None
    verify_ssl: bool = True

    def __post_init__(self):
        if self.headers is None:
            self.headers = {}


@dataclass
class AsyncResult:
    """Result wrapper for async operations."""

    success: bool
    data: Any = None
    error: Optional[str] = None
    duration: float = 0.0
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class AsyncRateLimiter:
    """
    Rate limiter for async operations.
    """

    def __init__(self, rate: float, burst: int = None):
        """
        Args:
            rate: Requests per second
            burst: Maximum burst size (defaults to rate)
        """
        self.rate = rate
        self.burst = burst or int(rate)
        self.tokens = self.burst
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Acquire permission to make a request."""
        async with self._lock:
            now = time.time()
            time_passed = now - self.last_update
            self.last_update = now

            # Add tokens based on time passed
            self.tokens = min(self.burst, self.tokens + time_passed * self.rate)

            if self.tokens >= 1:
                self.tokens -= 1
                return

            # Wait until we can get a token
            wait_time = (1 - self.tokens) / self.rate
            await asyncio.sleep(wait_time)
            self.tokens = 0


class AsyncRetryHandler:
    """
    Handles retry logic with exponential backoff.
    """

    def __init__(self, max_retries: int = 3, backoff_factor: float = 1.0):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    async def execute(
        self,
        coro_func: Callable[[], Awaitable[Any]],
        should_retry: Callable[[Exception], bool] = None,
    ) -> Any:
        """Execute a coroutine with retry logic."""
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return await coro_func()
            except Exception as e:
                last_exception = e

                if attempt >= self.max_retries:
                    raise

                if should_retry and not should_retry(e):
                    raise

                # Exponential backoff
                wait_time = self.backoff_factor * (2**attempt)
                await asyncio.sleep(wait_time)

        raise last_exception


class AsyncHTTPClient:
    """
    Async HTTP client with connection pooling, retries, and rate limiting.
    """

    def __init__(
        self, config: RequestConfig = None, rate_limiter: AsyncRateLimiter = None
    ):
        self.config = config or RequestConfig()
        self.rate_limiter = rate_limiter
        self.retry_handler = AsyncRetryHandler(
            self.config.retries, self.config.backoff_factor
        )
        self._session: Optional[aiohttp.ClientSession] = None
        self._session_lock = asyncio.Lock()

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            async with self._session_lock:
                if self._session is None or self._session.closed:
                    connector = aiohttp.TCPConnector(
                        limit=100,
                        limit_per_host=30,
                        ttl_dns_cache=300,
                        use_dns_cache=True,
                        verify_ssl=self.config.verify_ssl,
                    )
                    timeout = aiohttp.ClientTimeout(total=self.config.timeout)
                    self._session = aiohttp.ClientSession(
                        connector=connector,
                        timeout=timeout,
                        headers=self.config.headers,
                    )

        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def request(self, method: str, url: str, **kwargs) -> AsyncResult:
        """Make an HTTP request."""
        start_time = time.time()

        try:
            if self.rate_limiter:
                await self.rate_limiter.acquire()

            async def make_request():
                session = await self.get_session()
                async with session.request(method, url, **kwargs) as response:
                    if response.status >= 400:
                        error_text = await response.text()
                        raise aiohttp.ClientResponseError(
                            request_info=response.request_info,
                            history=response.history,
                            status=response.status,
                            message=error_text,
                        )

                    # Try to parse as JSON, fall back to text
                    content_type = response.headers.get("content-type", "").lower()
                    if "application/json" in content_type:
                        return await response.json()
                    else:
                        return await response.text()

            def should_retry(error: Exception) -> bool:
                if isinstance(error, aiohttp.ClientResponseError):
                    # Retry on server errors and rate limits
                    return error.status >= 500 or error.status == 429
                elif isinstance(
                    error, (aiohttp.ClientConnectionError, asyncio.TimeoutError)
                ):
                    return True
                return False

            data = await self.retry_handler.execute(make_request, should_retry)
            duration = time.time() - start_time

            return AsyncResult(success=True, data=data, duration=duration)

        except Exception as e:
            duration = time.time() - start_time
            return AsyncResult(success=False, error=str(e), duration=duration)

    async def get(self, url: str, **kwargs) -> AsyncResult:
        """Make a GET request."""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> AsyncResult:
        """Make a POST request."""
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> AsyncResult:
        """Make a PUT request."""
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> AsyncResult:
        """Make a DELETE request."""
        return await self.request("DELETE", url, **kwargs)


class AsyncFileManager:
    """
    Async file operations with batching and concurrent processing.
    """

    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def read_file(self, file_path: str, encoding: str = "utf-8") -> AsyncResult:
        """Read a file asynchronously."""
        start_time = time.time()

        try:
            async with self._semaphore:
                async with aiofiles.open(file_path, "r", encoding=encoding) as f:
                    content = await f.read()

                duration = time.time() - start_time
                return AsyncResult(success=True, data=content, duration=duration)

        except Exception as e:
            duration = time.time() - start_time
            return AsyncResult(success=False, error=str(e), duration=duration)

    async def write_file(
        self, file_path: str, content: str, encoding: str = "utf-8"
    ) -> AsyncResult:
        """Write to a file asynchronously."""
        start_time = time.time()

        try:
            async with self._semaphore:
                async with aiofiles.open(file_path, "w", encoding=encoding) as f:
                    await f.write(content)

                duration = time.time() - start_time
                return AsyncResult(success=True, data=len(content), duration=duration)

        except Exception as e:
            duration = time.time() - start_time
            return AsyncResult(success=False, error=str(e), duration=duration)

    async def read_json_file(self, file_path: str) -> AsyncResult:
        """Read and parse a JSON file asynchronously."""
        result = await self.read_file(file_path)

        if result.success:
            try:
                result.data = json.loads(result.data)
            except json.JSONDecodeError as e:
                result.success = False
                result.error = f"JSON decode error: {e}"

        return result

    async def write_json_file(self, file_path: str, data: Any) -> AsyncResult:
        """Write data to a JSON file asynchronously."""
        try:
            content = json.dumps(data, indent=2, default=str)
            return await self.write_file(file_path, content)
        except Exception as e:
            return AsyncResult(success=False, error=f"JSON encode error: {e}")

    async def read_multiple_files(self, file_paths: List[str]) -> List[AsyncResult]:
        """Read multiple files concurrently."""
        tasks = [self.read_file(path) for path in file_paths]
        return await asyncio.gather(*tasks)

    async def write_multiple_files(self, file_data: List[tuple]) -> List[AsyncResult]:
        """Write multiple files concurrently. file_data: [(path, content), ...]"""
        tasks = [self.write_file(path, content) for path, content in file_data]
        return await asyncio.gather(*tasks)


class AsyncTaskQueue:
    """
    Task queue for managing async operations with priority and rate limiting.
    """

    def __init__(self, max_concurrent: int = 10, rate_limiter: AsyncRateLimiter = None):
        self.max_concurrent = max_concurrent
        self.rate_limiter = rate_limiter
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._queue: asyncio.Queue = asyncio.Queue()
        self._workers: List[asyncio.Task] = []
        self._running = False
        self._results: Dict[str, AsyncResult] = {}
        self._result_callbacks: Dict[str, List[Callable]] = {}

    async def start(self):
        """Start the task queue workers."""
        if self._running:
            return

        self._running = True
        self._workers = [
            asyncio.create_task(self._worker(f"worker-{i}"))
            for i in range(self.max_concurrent)
        ]

    async def stop(self):
        """Stop the task queue workers."""
        self._running = False

        # Cancel all workers
        for worker in self._workers:
            worker.cancel()

        # Wait for workers to finish
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []

    async def _worker(self, worker_id: str):
        """Worker coroutine that processes tasks from the queue."""
        while self._running:
            try:
                task_id, coro_func, priority = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )

                if self.rate_limiter:
                    await self.rate_limiter.acquire()

                async with self._semaphore:
                    try:
                        result = await coro_func()
                        async_result = AsyncResult(success=True, data=result)
                    except Exception as e:
                        async_result = AsyncResult(success=False, error=str(e))

                    self._results[task_id] = async_result

                    # Call callbacks
                    for callback in self._result_callbacks.get(task_id, []):
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(async_result)
                            else:
                                callback(async_result)
                        except Exception:
                            pass  # Don't let callback errors break the worker

                self._queue.task_done()

            except asyncio.TimeoutError:
                continue
            except Exception:
                continue

    async def submit(
        self,
        task_id: str,
        coro_func: Callable[[], Awaitable[Any]],
        priority: int = 0,
        callback: Callable = None,
    ) -> str:
        """Submit a task to the queue."""
        if not self._running:
            await self.start()

        if callback:
            self._result_callbacks.setdefault(task_id, []).append(callback)

        await self._queue.put((task_id, coro_func, priority))
        return task_id

    def get_result(self, task_id: str) -> Optional[AsyncResult]:
        """Get the result of a completed task."""
        return self._results.get(task_id)

    async def wait_for_result(
        self, task_id: str, timeout: float = None
    ) -> Optional[AsyncResult]:
        """Wait for a task result with optional timeout."""
        start_time = time.time()

        while True:
            if task_id in self._results:
                return self._results[task_id]

            if timeout and (time.time() - start_time) >= timeout:
                return None

            await asyncio.sleep(0.1)

    def get_queue_size(self) -> int:
        """Get the current queue size."""
        return self._queue.qsize()


class AsyncBatch:
    """
    Utility for batching async operations.
    """

    def __init__(self, batch_size: int = 10, max_concurrent: int = 5):
        self.batch_size = batch_size
        self.max_concurrent = max_concurrent

    async def process_batch(
        self, items: List[Any], async_func: Callable[[Any], Awaitable[Any]]
    ) -> List[AsyncResult]:
        """Process items in batches with concurrent execution."""
        results = []

        # Process items in batches
        for i in range(0, len(items), self.batch_size):
            batch = items[i : i + self.batch_size]

            # Create semaphore for this batch
            semaphore = asyncio.Semaphore(self.max_concurrent)

            async def process_item(item):
                async with semaphore:
                    start_time = time.time()
                    try:
                        data = await async_func(item)
                        duration = time.time() - start_time
                        return AsyncResult(success=True, data=data, duration=duration)
                    except Exception as e:
                        duration = time.time() - start_time
                        return AsyncResult(
                            success=False, error=str(e), duration=duration
                        )

            # Process batch concurrently
            batch_results = await asyncio.gather(
                *[process_item(item) for item in batch]
            )
            results.extend(batch_results)

        return results


def async_to_sync(async_func: Callable[..., Awaitable[Any]]) -> Callable[..., Any]:
    """
    Decorator to convert async function to sync by running in event loop.
    """

    @wraps(async_func)
    def wrapper(*args, **kwargs):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(async_func(*args, **kwargs))

    return wrapper


def run_async_in_thread(
    async_func: Callable[..., Awaitable[Any]], *args, **kwargs
) -> Any:
    """
    Run an async function in a separate thread with its own event loop.
    """
    result_queue = queue.Queue()

    def thread_target():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(async_func(*args, **kwargs))
            result_queue.put(("success", result))
        except Exception as e:
            result_queue.put(("error", e))
        finally:
            loop.close()

    thread = threading.Thread(target=thread_target)
    thread.start()
    thread.join()

    status, result = result_queue.get()
    if status == "error":
        raise result
    return result


# Global instances for convenience
_global_http_client: Optional[AsyncHTTPClient] = None
_global_file_manager: Optional[AsyncFileManager] = None
_global_task_queue: Optional[AsyncTaskQueue] = None


def get_http_client() -> AsyncHTTPClient:
    """Get the global HTTP client instance."""
    global _global_http_client
    if _global_http_client is None:
        _global_http_client = AsyncHTTPClient()
    return _global_http_client


def get_file_manager() -> AsyncFileManager:
    """Get the global file manager instance."""
    global _global_file_manager
    if _global_file_manager is None:
        _global_file_manager = AsyncFileManager()
    return _global_file_manager


def get_task_queue() -> AsyncTaskQueue:
    """Get the global task queue instance."""
    global _global_task_queue
    if _global_task_queue is None:
        _global_task_queue = AsyncTaskQueue()
    return _global_task_queue


if __name__ == "__main__":
    # Example usage
    async def main():
        # File operations example
        file_manager = AsyncFileManager()
        write_result = await file_manager.write_json_file("test.json", {"test": "data"})
        print(f"Write Result: {write_result.success}")

        if write_result.success:
            read_result = await file_manager.read_json_file("test.json")
            print(f"Read Result: {read_result.success}, Data: {read_result.data}")

        # Task queue example
        task_queue = AsyncTaskQueue()
        await task_queue.start()

        async def test_task():
            await asyncio.sleep(1)
            return "Task completed"

        task_id = await task_queue.submit("test-task", test_task)
        result = await task_queue.wait_for_result(task_id, timeout=5)
        print(
            f"Task Result: {result.success}, Data: {result.data if result and result.success else 'Failed'}"
        )

        await task_queue.stop()

    # Run the example
    asyncio.run(main())
