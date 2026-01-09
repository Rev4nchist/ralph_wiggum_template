"""
Stress Test Runner Harness

Provides utilities for running stress tests with:
- Concurrent agent simulation
- Metrics collection
- Progress reporting
- Failure detection
"""
import asyncio
import time
import threading
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, List, Dict, Any, Optional
from enum import Enum


class TestStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


@dataclass
class AgentResult:
    agent_id: str
    success: bool
    operations_count: int
    errors: List[str]
    latencies_ms: List[float]
    duration_seconds: float
    custom_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StressTestResult:
    test_id: str
    status: TestStatus
    duration_seconds: float
    total_agents: int
    successful_agents: int
    failed_agents: int
    total_operations: int
    total_errors: int
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    agent_results: List[AgentResult]
    failure_reasons: List[str]
    custom_metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        return self.successful_agents / self.total_agents if self.total_agents > 0 else 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "status": self.status.value,
            "duration_seconds": self.duration_seconds,
            "total_agents": self.total_agents,
            "successful_agents": self.successful_agents,
            "failed_agents": self.failed_agents,
            "success_rate": self.success_rate,
            "total_operations": self.total_operations,
            "total_errors": self.total_errors,
            "latency_p50_ms": self.latency_p50_ms,
            "latency_p95_ms": self.latency_p95_ms,
            "latency_p99_ms": self.latency_p99_ms,
            "failure_reasons": self.failure_reasons,
            "custom_metrics": self.custom_metrics
        }


class StressTestRunner:

    def __init__(self, test_id: str, max_workers: int = 100):
        self.test_id = test_id
        self.max_workers = max_workers
        self._executor: Optional[ThreadPoolExecutor] = None
        self._lock = threading.Lock()
        self._agent_results: List[AgentResult] = []

    def run_concurrent(
        self,
        agent_count: int,
        agent_task: Callable[[str, int], AgentResult],
        timeout_seconds: int = 300
    ) -> StressTestResult:
        start_time = time.time()
        self._agent_results = []

        with ThreadPoolExecutor(max_workers=min(agent_count, self.max_workers)) as executor:
            futures = {
                executor.submit(agent_task, f"agent-{i}", i): i
                for i in range(agent_count)
            }

            for future in as_completed(futures, timeout=timeout_seconds):
                try:
                    result = future.result(timeout=10)
                    with self._lock:
                        self._agent_results.append(result)
                except Exception as e:
                    agent_idx = futures[future]
                    with self._lock:
                        self._agent_results.append(AgentResult(
                            agent_id=f"agent-{agent_idx}",
                            success=False,
                            operations_count=0,
                            errors=[str(e)],
                            latencies_ms=[],
                            duration_seconds=0
                        ))

        return self._compile_results(start_time)

    def run_waves(
        self,
        waves: List[List[Callable[[str], AgentResult]]],
        timeout_per_wave: int = 60
    ) -> StressTestResult:
        start_time = time.time()
        self._agent_results = []

        for wave_idx, wave_tasks in enumerate(waves):
            wave_results = []
            with ThreadPoolExecutor(max_workers=len(wave_tasks)) as executor:
                futures = {
                    executor.submit(task, f"wave{wave_idx}-agent-{i}"): i
                    for i, task in enumerate(wave_tasks)
                }

                for future in as_completed(futures, timeout=timeout_per_wave):
                    try:
                        result = future.result(timeout=10)
                        wave_results.append(result)
                    except Exception as e:
                        agent_idx = futures[future]
                        wave_results.append(AgentResult(
                            agent_id=f"wave{wave_idx}-agent-{agent_idx}",
                            success=False,
                            operations_count=0,
                            errors=[str(e)],
                            latencies_ms=[],
                            duration_seconds=0
                        ))

            self._agent_results.extend(wave_results)

            all_success = all(r.success for r in wave_results)
            if not all_success:
                break

        return self._compile_results(start_time)

    def _compile_results(self, start_time: float) -> StressTestResult:
        duration = time.time() - start_time

        successful = [r for r in self._agent_results if r.success]
        failed = [r for r in self._agent_results if not r.success]

        all_latencies = []
        for r in self._agent_results:
            all_latencies.extend(r.latencies_ms)

        all_latencies.sort()
        if all_latencies:
            p50 = all_latencies[int(len(all_latencies) * 0.50)]
            p95 = all_latencies[int(len(all_latencies) * 0.95)]
            p99 = all_latencies[int(len(all_latencies) * 0.99)]
        else:
            p50 = p95 = p99 = 0

        total_ops = sum(r.operations_count for r in self._agent_results)
        total_errors = sum(len(r.errors) for r in self._agent_results)

        failure_reasons = []
        for r in failed:
            failure_reasons.extend(r.errors[:3])

        status = TestStatus.PASSED if len(failed) == 0 else TestStatus.FAILED

        return StressTestResult(
            test_id=self.test_id,
            status=status,
            duration_seconds=duration,
            total_agents=len(self._agent_results),
            successful_agents=len(successful),
            failed_agents=len(failed),
            total_operations=total_ops,
            total_errors=total_errors,
            latency_p50_ms=p50,
            latency_p95_ms=p95,
            latency_p99_ms=p99,
            agent_results=self._agent_results,
            failure_reasons=failure_reasons[:10]
        )


class WaveBuilder:

    def __init__(self, tasks: List[Dict[str, Any]]):
        self.tasks = {t["id"]: t for t in tasks}
        self.waves: List[List[str]] = []

    def build(self) -> List[List[str]]:
        completed = set()
        remaining = set(self.tasks.keys())

        while remaining:
            wave = []
            for task_id in list(remaining):
                task = self.tasks[task_id]
                deps = set(task.get("deps", []))
                if deps <= completed:
                    wave.append(task_id)

            if not wave:
                raise ValueError(f"Circular dependency detected. Remaining: {remaining}")

            self.waves.append(wave)
            completed.update(wave)
            remaining -= set(wave)

        return self.waves

    def get_wave_count(self) -> int:
        if not self.waves:
            self.build()
        return len(self.waves)


def calculate_fairness(values: List[int]) -> float:
    if not values or len(values) < 2:
        return 1.0
    mean = statistics.mean(values)
    if mean == 0:
        return 1.0
    std_dev = statistics.stdev(values)
    cv = std_dev / mean
    return max(0, 1 - cv)


def detect_deadlock(agent_states: Dict[str, str], timeout_seconds: int = 30) -> List[str]:
    stuck_agents = []
    for agent_id, state in agent_states.items():
        if state == "waiting" or state == "blocked":
            stuck_agents.append(agent_id)
    return stuck_agents
