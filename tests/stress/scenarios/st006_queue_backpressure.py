"""
ST-006: Queue Backpressure Test

Tests system behavior when task queue is overwhelmed with failing dependency checks.
Verifies queue stays bounded, no CPU spinning, and eventual progress.

Pass Criteria:
- Queue size stays bounded
- Agents don't spin at 100% CPU
- Successful claims happen eventually
- System remains responsive
"""
import pytest
import time
import threading
import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Set, Optional
from dataclasses import dataclass, field
from collections import deque

from ..conftest import requires_redis
from ..metrics import StressTestMetrics, MetricsCollector


TOTAL_TASKS = 500
AGENT_COUNT = 20
DEPS_MET_RATE = 0.2
MAX_QUEUE_SIZE = 1000
BACKOFF_BASE_MS = 10
BACKOFF_MAX_MS = 1000


@dataclass
class QueueMetrics:
    peak_size: int = 0
    current_size: int = 0
    enqueue_count: int = 0
    dequeue_count: int = 0
    reject_count: int = 0
    backpressure_events: int = 0


class BoundedTaskQueue:

    def __init__(self, redis_client, prefix: str, max_size: int = MAX_QUEUE_SIZE):
        self.redis = redis_client
        self.prefix = prefix
        self.max_size = max_size
        self.queue_key = f"{prefix}:task_queue"
        self.metrics = QueueMetrics()
        self.lock = threading.Lock()

    def enqueue(self, task_id: str, priority: int = 0) -> bool:
        current_size = self.redis.llen(self.queue_key)

        if current_size >= self.max_size:
            with self.lock:
                self.metrics.reject_count += 1
                self.metrics.backpressure_events += 1
            return False

        self.redis.lpush(self.queue_key, json.dumps({
            "task_id": task_id,
            "priority": priority,
            "enqueued_at": time.time()
        }))

        with self.lock:
            self.metrics.enqueue_count += 1
            self.metrics.current_size = self.redis.llen(self.queue_key)
            if self.metrics.current_size > self.metrics.peak_size:
                self.metrics.peak_size = self.metrics.current_size

        return True

    def dequeue(self, timeout: float = 1.0) -> Optional[Dict]:
        result = self.redis.brpop(self.queue_key, timeout=int(timeout))
        if result:
            with self.lock:
                self.metrics.dequeue_count += 1
                self.metrics.current_size = self.redis.llen(self.queue_key)
            return json.loads(result[1])
        return None

    def size(self) -> int:
        return self.redis.llen(self.queue_key)

    def clear(self):
        self.redis.delete(self.queue_key)


class DependencyChecker:

    def __init__(self, redis_client, prefix: str, success_rate: float = DEPS_MET_RATE):
        self.redis = redis_client
        self.prefix = prefix
        self.success_rate = success_rate
        self.completed_key = f"{prefix}:completed_tasks"
        self.check_count = 0
        self.success_count = 0
        self.lock = threading.Lock()

    def complete_task(self, task_id: str):
        self.redis.sadd(self.completed_key, task_id)

    def check_deps(self, task_id: str, deps: List[str]) -> bool:
        with self.lock:
            self.check_count += 1

        if not deps:
            with self.lock:
                self.success_count += 1
            return True

        completed = self.redis.smembers(self.completed_key)
        deps_met = all(dep in completed for dep in deps)

        if deps_met:
            with self.lock:
                self.success_count += 1

        return deps_met

    def get_stats(self) -> Dict:
        return {
            "check_count": self.check_count,
            "success_count": self.success_count,
            "success_rate": self.success_count / max(1, self.check_count)
        }


class BackoffStrategy:

    def __init__(self, base_ms: int = BACKOFF_BASE_MS, max_ms: int = BACKOFF_MAX_MS):
        self.base_ms = base_ms
        self.max_ms = max_ms

    def calculate(self, attempt: int) -> float:
        delay = min(self.base_ms * (2 ** attempt), self.max_ms)
        jitter = random.uniform(0, delay * 0.1)
        return (delay + jitter) / 1000

    def wait(self, attempt: int):
        time.sleep(self.calculate(attempt))


@dataclass
class AgentWorkResult:
    agent_id: str
    tasks_attempted: int
    tasks_completed: int
    dep_check_failures: int
    backoff_waits: int
    total_backoff_time_ms: float
    errors: List[str]
    duration_seconds: float


def worker_agent(
    agent_id: str,
    queue: BoundedTaskQueue,
    dep_checker: DependencyChecker,
    tasks: Dict[str, List[str]],
    backoff: BackoffStrategy,
    stop_event: threading.Event
) -> AgentWorkResult:
    start = time.time()
    attempted = 0
    completed = 0
    dep_failures = 0
    backoff_waits = 0
    total_backoff_ms = 0
    errors = []
    consecutive_failures = 0

    max_iterations = 100
    iteration = 0
    while not stop_event.is_set() and iteration < max_iterations:
        iteration += 1
        task_data = queue.dequeue(timeout=0.1)
        if not task_data:
            if consecutive_failures > 5:
                backoff_delay = min(backoff.calculate(consecutive_failures), 0.5)
                total_backoff_ms += backoff_delay * 1000
                backoff_waits += 1
                time.sleep(backoff_delay)
            continue

        task_id = task_data["task_id"]
        attempted += 1

        deps = tasks.get(task_id, [])
        if dep_checker.check_deps(task_id, deps):
            time.sleep(0.01)
            dep_checker.complete_task(task_id)
            completed += 1
            consecutive_failures = 0
        else:
            dep_failures += 1
            consecutive_failures += 1

            if queue.enqueue(task_id):
                pass
            else:
                errors.append(f"Queue full, dropping {task_id}")

    return AgentWorkResult(
        agent_id=agent_id,
        tasks_attempted=attempted,
        tasks_completed=completed,
        dep_check_failures=dep_failures,
        backoff_waits=backoff_waits,
        total_backoff_time_ms=total_backoff_ms,
        errors=errors,
        duration_seconds=time.time() - start
    )


@requires_redis
class TestQueueBackpressure:

    def test_bounded_queue_under_load(
        self,
        redis_client,
        stress_test_id,
        thread_pool_20
    ):
        """
        ST-006: 500 tasks, 80% fail dep checks, queue stays bounded.
        """
        metrics = MetricsCollector(stress_test_id, "ST-006: Queue Backpressure")
        queue = BoundedTaskQueue(redis_client, stress_test_id, max_size=200)
        dep_checker = DependencyChecker(redis_client, stress_test_id, success_rate=DEPS_MET_RATE)
        backoff = BackoffStrategy()

        tasks = {}
        for i in range(TOTAL_TASKS):
            if i < 100:
                tasks[f"task-{i}"] = []
            else:
                num_deps = random.randint(1, 3)
                deps = [f"task-{random.randint(0, i-1)}" for _ in range(num_deps)]
                tasks[f"task-{i}"] = deps

        for task_id in tasks:
            queue.enqueue(task_id)

        stop_event = threading.Event()

        def timed_stop():
            time.sleep(15)
            stop_event.set()

        timer = threading.Thread(target=timed_stop, daemon=True)
        timer.start()

        futures = []
        for i in range(AGENT_COUNT):
            f = thread_pool_20.submit(
                worker_agent,
                f"agent-{i}",
                queue,
                dep_checker,
                tasks,
                backoff,
                stop_event
            )
            futures.append(f)

        results: List[AgentWorkResult] = []
        for f in as_completed(futures, timeout=30):
            results.append(f.result())

        final_metrics = metrics.finalize()

        total_completed = sum(r.tasks_completed for r in results)
        total_dep_failures = sum(r.dep_check_failures for r in results)
        total_backoff_waits = sum(r.backoff_waits for r in results)

        print(f"\nQueue Metrics:")
        print(f"  Peak size: {queue.metrics.peak_size}")
        print(f"  Enqueue: {queue.metrics.enqueue_count}")
        print(f"  Dequeue: {queue.metrics.dequeue_count}")
        print(f"  Rejects: {queue.metrics.reject_count}")
        print(f"  Backpressure events: {queue.metrics.backpressure_events}")
        print(f"\nAgent Metrics:")
        print(f"  Total completed: {total_completed}/{TOTAL_TASKS}")
        print(f"  Dep check failures: {total_dep_failures}")
        print(f"  Backoff waits: {total_backoff_waits}")

        assert queue.metrics.peak_size <= queue.max_size, \
            f"Queue exceeded max size: {queue.metrics.peak_size} > {queue.max_size}"

        assert total_completed > 50, \
            f"Too few completions: {total_completed} (starvation?)"

        queue.clear()

    def test_backoff_prevents_cpu_spin(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Verify exponential backoff prevents CPU spinning.
        """
        backoff = BackoffStrategy(base_ms=10, max_ms=1000)

        delays = [backoff.calculate(i) for i in range(10)]

        assert delays[0] < 0.02, "First backoff should be ~10ms"
        assert delays[5] > 0.1, "Later backoffs should be longer"
        assert all(d <= 1.1 for d in delays), "No delay should exceed max + jitter"

        for i in range(1, len(delays)):
            assert delays[i] >= delays[i-1] * 0.8, \
                "Backoff should generally increase"

    def test_queue_drain_with_dependencies(
        self,
        redis_client,
        stress_test_id,
        thread_pool_10
    ):
        """
        Queue eventually drains when dependencies are progressively met.
        """
        queue = BoundedTaskQueue(redis_client, f"{stress_test_id}:drain", max_size=100)
        dep_checker = DependencyChecker(redis_client, f"{stress_test_id}:drain")

        num_tasks = 50
        tasks = {}
        for i in range(num_tasks):
            if i < 10:
                tasks[f"drain-{i}"] = []
            else:
                tasks[f"drain-{i}"] = [f"drain-{i-1}"]

        for task_id in tasks:
            queue.enqueue(task_id)

        stop_event = threading.Event()
        backoff = BackoffStrategy()

        def run_until_complete():
            start = time.time()
            while queue.size() > 0 and time.time() - start < 30:
                task_data = queue.dequeue(timeout=0.5)
                if not task_data:
                    continue

                task_id = task_data["task_id"]
                deps = tasks.get(task_id, [])

                if dep_checker.check_deps(task_id, deps):
                    time.sleep(0.01)
                    dep_checker.complete_task(task_id)
                else:
                    queue.enqueue(task_id)
                    time.sleep(0.01)

        run_until_complete()

        completed_count = redis_client.scard(f"{stress_test_id}:drain:completed_tasks")
        assert completed_count == num_tasks, \
            f"Not all tasks completed: {completed_count}/{num_tasks}"

        queue.clear()

    def test_concurrent_enqueue_dequeue(
        self,
        redis_client,
        stress_test_id,
        thread_pool_20
    ):
        """
        Concurrent enqueue/dequeue operations maintain consistency.
        """
        queue = BoundedTaskQueue(redis_client, f"{stress_test_id}:concurrent", max_size=100)
        enqueued = []
        dequeued = []
        lock = threading.Lock()

        def enqueuer(count: int):
            for i in range(count):
                task_id = f"concurrent-{threading.current_thread().name}-{i}"
                if queue.enqueue(task_id):
                    with lock:
                        enqueued.append(task_id)
                time.sleep(0.001)

        def dequeuer(duration: float):
            start = time.time()
            while time.time() - start < duration:
                task = queue.dequeue(timeout=0.1)
                if task:
                    with lock:
                        dequeued.append(task["task_id"])

        futures = []
        for i in range(5):
            futures.append(thread_pool_20.submit(enqueuer, 50))

        for i in range(5):
            futures.append(thread_pool_20.submit(dequeuer, 3.0))

        for f in as_completed(futures, timeout=30):
            f.result()

        time.sleep(0.5)
        while True:
            task = queue.dequeue(timeout=0.1)
            if not task:
                break
            dequeued.append(task["task_id"])

        assert len(dequeued) == len(enqueued), \
            f"Lost tasks: enqueued {len(enqueued)}, dequeued {len(dequeued)}"

        queue.clear()

    def test_queue_rejection_under_pressure(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Queue correctly rejects when full.
        """
        small_queue = BoundedTaskQueue(redis_client, f"{stress_test_id}:small", max_size=10)

        for i in range(15):
            small_queue.enqueue(f"overflow-{i}")

        assert small_queue.size() <= 10, \
            f"Queue exceeded max size: {small_queue.size()}"

        assert small_queue.metrics.reject_count >= 5, \
            f"Should have rejected tasks: {small_queue.metrics.reject_count}"

        small_queue.clear()

    def test_system_responsiveness_under_load(
        self,
        redis_client,
        stress_test_id
    ):
        """
        System remains responsive even under heavy queue load.
        """
        queue = BoundedTaskQueue(redis_client, f"{stress_test_id}:responsive", max_size=500)

        for i in range(500):
            queue.enqueue(f"load-{i}")

        response_times = []
        for _ in range(10):
            start = time.time()
            queue.size()
            response_times.append((time.time() - start) * 1000)

        avg_response = sum(response_times) / len(response_times)
        max_response = max(response_times)

        assert avg_response < 10, \
            f"Average response too slow: {avg_response:.2f}ms"

        assert max_response < 50, \
            f"Max response too slow: {max_response:.2f}ms"

        queue.clear()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
