"""
Stress Test Metrics Collection

Provides:
- StressTestMetrics dataclass for standardized metrics
- Latency calculations (p50, p95, p99)
- Success rate calculations
- Redis memory tracking
- Report generation
"""
import time
import json
import statistics
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class OperationMetric:
    operation_type: str
    timestamp: float
    latency_ms: float
    success: bool
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StressTestMetrics:
    test_id: str
    test_name: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    operations: List[OperationMetric] = field(default_factory=list)
    custom_counters: Dict[str, int] = field(default_factory=dict)
    custom_gauges: Dict[str, float] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def operations_total(self) -> int:
        return len(self.operations)

    @property
    def operations_success(self) -> int:
        return sum(1 for op in self.operations if op.success)

    @property
    def operations_failed(self) -> int:
        return sum(1 for op in self.operations if not op.success)

    @property
    def success_rate(self) -> float:
        if self.operations_total == 0:
            return 0.0
        return self.operations_success / self.operations_total

    @property
    def latencies_ms(self) -> List[float]:
        return [op.latency_ms for op in self.operations if op.success]

    def latency_percentile(self, percentile: float) -> float:
        latencies = sorted(self.latencies_ms)
        if not latencies:
            return 0.0
        idx = int(len(latencies) * percentile / 100)
        return latencies[min(idx, len(latencies) - 1)]

    @property
    def latency_p50_ms(self) -> float:
        return self.latency_percentile(50)

    @property
    def latency_p95_ms(self) -> float:
        return self.latency_percentile(95)

    @property
    def latency_p99_ms(self) -> float:
        return self.latency_percentile(99)

    @property
    def latency_avg_ms(self) -> float:
        latencies = self.latencies_ms
        if not latencies:
            return 0.0
        return statistics.mean(latencies)

    @property
    def latency_max_ms(self) -> float:
        latencies = self.latencies_ms
        if not latencies:
            return 0.0
        return max(latencies)

    @property
    def throughput_ops_per_sec(self) -> float:
        if self.duration_seconds == 0:
            return 0.0
        return self.operations_total / self.duration_seconds

    def record_operation(
        self,
        operation_type: str,
        latency_ms: float,
        success: bool,
        error: str = None,
        metadata: Dict[str, Any] = None
    ):
        self.operations.append(OperationMetric(
            operation_type=operation_type,
            timestamp=time.time(),
            latency_ms=latency_ms,
            success=success,
            error=error,
            metadata=metadata or {}
        ))
        if not success and error:
            self.errors.append(error)

    def increment_counter(self, name: str, value: int = 1):
        self.custom_counters[name] = self.custom_counters.get(name, 0) + value

    def set_gauge(self, name: str, value: float):
        self.custom_gauges[name] = value

    def add_error(self, error: str):
        self.errors.append(error)

    def add_warning(self, warning: str):
        self.warnings.append(warning)

    def finalize(self):
        self.end_time = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "test_name": self.test_name,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
            "duration_seconds": round(self.duration_seconds, 3),
            "operations_total": self.operations_total,
            "operations_success": self.operations_success,
            "operations_failed": self.operations_failed,
            "success_rate": round(self.success_rate, 4),
            "latency_p50_ms": round(self.latency_p50_ms, 2),
            "latency_p95_ms": round(self.latency_p95_ms, 2),
            "latency_p99_ms": round(self.latency_p99_ms, 2),
            "latency_avg_ms": round(self.latency_avg_ms, 2),
            "latency_max_ms": round(self.latency_max_ms, 2),
            "throughput_ops_per_sec": round(self.throughput_ops_per_sec, 2),
            "custom_counters": self.custom_counters,
            "custom_gauges": {k: round(v, 4) for k, v in self.custom_gauges.items()},
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors[:20],
            "warnings": self.warnings[:20]
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def print_summary(self):
        print(f"\n{'='*60}")
        print(f"STRESS TEST RESULTS: {self.test_name}")
        print(f"{'='*60}")
        print(f"Duration: {self.duration_seconds:.2f}s")
        print(f"Operations: {self.operations_success}/{self.operations_total} ({self.success_rate*100:.1f}%)")
        print(f"Throughput: {self.throughput_ops_per_sec:.1f} ops/sec")
        print(f"Latency p50: {self.latency_p50_ms:.2f}ms")
        print(f"Latency p95: {self.latency_p95_ms:.2f}ms")
        print(f"Latency p99: {self.latency_p99_ms:.2f}ms")
        print(f"Latency max: {self.latency_max_ms:.2f}ms")
        if self.custom_counters:
            print(f"Counters: {self.custom_counters}")
        if self.custom_gauges:
            print(f"Gauges: {self.custom_gauges}")
        if self.errors:
            print(f"Errors ({len(self.errors)}): {self.errors[:5]}")
        print(f"{'='*60}\n")


class MetricsCollector:

    def __init__(self, test_id: str, test_name: str):
        self.metrics = StressTestMetrics(test_id=test_id, test_name=test_name)
        self._operation_start: Dict[str, float] = {}

    def start_operation(self, operation_id: str):
        self._operation_start[operation_id] = time.time()

    def end_operation(
        self,
        operation_id: str,
        operation_type: str,
        success: bool,
        error: str = None,
        metadata: Dict[str, Any] = None
    ):
        start = self._operation_start.pop(operation_id, time.time())
        latency_ms = (time.time() - start) * 1000
        self.metrics.record_operation(
            operation_type=operation_type,
            latency_ms=latency_ms,
            success=success,
            error=error,
            metadata=metadata
        )

    def record_instant(
        self,
        operation_type: str,
        latency_ms: float,
        success: bool,
        error: str = None
    ):
        self.metrics.record_operation(
            operation_type=operation_type,
            latency_ms=latency_ms,
            success=success,
            error=error
        )

    def finalize(self) -> StressTestMetrics:
        self.metrics.finalize()
        return self.metrics


def assert_metrics_pass(metrics: StressTestMetrics, criteria: Dict[str, Any]):
    failures = []

    if "min_success_rate" in criteria:
        if metrics.success_rate < criteria["min_success_rate"]:
            failures.append(
                f"Success rate {metrics.success_rate:.2%} < {criteria['min_success_rate']:.2%}"
            )

    if "max_latency_p99_ms" in criteria:
        if metrics.latency_p99_ms > criteria["max_latency_p99_ms"]:
            failures.append(
                f"p99 latency {metrics.latency_p99_ms:.2f}ms > {criteria['max_latency_p99_ms']}ms"
            )

    if "max_error_count" in criteria:
        if len(metrics.errors) > criteria["max_error_count"]:
            failures.append(
                f"Error count {len(metrics.errors)} > {criteria['max_error_count']}"
            )

    if "min_throughput_ops_per_sec" in criteria:
        if metrics.throughput_ops_per_sec < criteria["min_throughput_ops_per_sec"]:
            failures.append(
                f"Throughput {metrics.throughput_ops_per_sec:.1f} < {criteria['min_throughput_ops_per_sec']}"
            )

    if failures:
        raise AssertionError(f"Metrics criteria not met:\n" + "\n".join(failures))
