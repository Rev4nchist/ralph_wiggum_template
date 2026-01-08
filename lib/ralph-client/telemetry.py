"""Telemetry and metrics for Ralph multi-agent platform."""
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from contextlib import contextmanager

try:
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False


@dataclass
class MetricSnapshot:
    """Point-in-time snapshot of metrics."""
    timestamp: datetime
    counters: Dict[str, int]
    histograms: Dict[str, list]
    gauges: Dict[str, float]


class SimpleMetrics:
    """Lightweight metrics implementation (no external deps)."""

    def __init__(self):
        self._counters: Dict[str, int] = {}
        self._histograms: Dict[str, list] = {}
        self._gauges: Dict[str, float] = {}
        self._start_time = time.time()

    def increment(self, name: str, value: int = 1, labels: Dict[str, str] = None):
        """Increment a counter."""
        key = self._make_key(name, labels)
        self._counters[key] = self._counters.get(key, 0) + value

    def record(self, name: str, value: float, labels: Dict[str, str] = None):
        """Record a value in a histogram."""
        key = self._make_key(name, labels)
        if key not in self._histograms:
            self._histograms[key] = []
        self._histograms[key].append(value)
        if len(self._histograms[key]) > 1000:
            self._histograms[key] = self._histograms[key][-1000:]

    def set_gauge(self, name: str, value: float, labels: Dict[str, str] = None):
        """Set a gauge value."""
        key = self._make_key(name, labels)
        self._gauges[key] = value

    def _make_key(self, name: str, labels: Dict[str, str] = None) -> str:
        """Create a unique key for a metric with labels."""
        if not labels:
            return name
        label_str = ','.join(f'{k}={v}' for k, v in sorted(labels.items()))
        return f'{name}{{{label_str}}}'

    def get_counter(self, name: str, labels: Dict[str, str] = None) -> int:
        """Get current counter value."""
        key = self._make_key(name, labels)
        return self._counters.get(key, 0)

    def get_histogram_stats(self, name: str, labels: Dict[str, str] = None) -> Dict[str, float]:
        """Get histogram statistics."""
        key = self._make_key(name, labels)
        values = self._histograms.get(key, [])
        if not values:
            return {'count': 0, 'min': 0, 'max': 0, 'avg': 0, 'p50': 0, 'p95': 0, 'p99': 0}

        sorted_vals = sorted(values)
        count = len(sorted_vals)

        return {
            'count': count,
            'min': sorted_vals[0],
            'max': sorted_vals[-1],
            'avg': sum(sorted_vals) / count,
            'p50': sorted_vals[int(count * 0.5)],
            'p95': sorted_vals[int(count * 0.95)] if count > 20 else sorted_vals[-1],
            'p99': sorted_vals[int(count * 0.99)] if count > 100 else sorted_vals[-1],
        }

    def snapshot(self) -> MetricSnapshot:
        """Get a snapshot of all metrics."""
        return MetricSnapshot(
            timestamp=datetime.utcnow(),
            counters=dict(self._counters),
            histograms={k: list(v) for k, v in self._histograms.items()},
            gauges=dict(self._gauges)
        )

    def reset(self):
        """Reset all metrics."""
        self._counters.clear()
        self._histograms.clear()
        self._gauges.clear()
        self._start_time = time.time()


class RalphMetrics:
    """Metrics collector for Ralph platform."""

    TASK_CLAIMS = 'ralph.tasks.claims'
    TASK_COMPLETIONS = 'ralph.tasks.completions'
    TASK_FAILURES = 'ralph.tasks.failures'
    TASK_CLAIM_LATENCY = 'ralph.tasks.claim_latency_ms'
    TASK_EXECUTION_TIME = 'ralph.tasks.execution_time_ms'

    LOCK_ACQUISITIONS = 'ralph.locks.acquisitions'
    LOCK_RELEASES = 'ralph.locks.releases'
    LOCK_CONTENTIONS = 'ralph.locks.contentions'
    LOCK_WAIT_TIME = 'ralph.locks.wait_time_ms'

    AGENT_REGISTRATIONS = 'ralph.agents.registrations'
    AGENT_HEARTBEATS = 'ralph.agents.heartbeats'
    ACTIVE_AGENTS = 'ralph.agents.active'

    REDIS_OPERATIONS = 'ralph.redis.operations'
    REDIS_ERRORS = 'ralph.redis.errors'
    REDIS_LATENCY = 'ralph.redis.latency_ms'

    def __init__(self, service_name: str = 'ralph-client'):
        self._service_name = service_name
        self._metrics = SimpleMetrics()

    def record_claim(self, agent_id: str, task_id: str, success: bool, latency_ms: float):
        """Record a task claim attempt."""
        labels = {'agent_id': agent_id, 'success': str(success).lower()}
        self._metrics.increment(self.TASK_CLAIMS, labels=labels)
        if success:
            self._metrics.record(self.TASK_CLAIM_LATENCY, latency_ms, labels={'agent_id': agent_id})

    def record_completion(self, agent_id: str, task_id: str, execution_time_ms: float):
        """Record a task completion."""
        labels = {'agent_id': agent_id}
        self._metrics.increment(self.TASK_COMPLETIONS, labels=labels)
        self._metrics.record(self.TASK_EXECUTION_TIME, execution_time_ms, labels=labels)

    def record_failure(self, agent_id: str, task_id: str, error_type: str):
        """Record a task failure."""
        labels = {'agent_id': agent_id, 'error_type': error_type}
        self._metrics.increment(self.TASK_FAILURES, labels=labels)

    def record_lock_acquired(self, agent_id: str, file_path: str, wait_time_ms: float = 0):
        """Record a lock acquisition."""
        labels = {'agent_id': agent_id}
        self._metrics.increment(self.LOCK_ACQUISITIONS, labels=labels)
        if wait_time_ms > 0:
            self._metrics.record(self.LOCK_WAIT_TIME, wait_time_ms, labels=labels)

    def record_lock_released(self, agent_id: str, file_path: str):
        """Record a lock release."""
        self._metrics.increment(self.LOCK_RELEASES, labels={'agent_id': agent_id})

    def record_lock_contention(self, agent_id: str, file_path: str, holder_id: str):
        """Record a lock contention event."""
        self._metrics.increment(self.LOCK_CONTENTIONS, labels={'agent_id': agent_id, 'holder': holder_id})

    def record_registration(self, agent_id: str, agent_type: str):
        """Record an agent registration."""
        self._metrics.increment(self.AGENT_REGISTRATIONS, labels={'agent_type': agent_type})

    def record_heartbeat(self, agent_id: str):
        """Record an agent heartbeat."""
        self._metrics.increment(self.AGENT_HEARTBEATS, labels={'agent_id': agent_id})

    def set_active_agents(self, count: int):
        """Set the current active agent count."""
        self._metrics.set_gauge(self.ACTIVE_AGENTS, count)

    def record_redis_operation(self, operation: str, success: bool, latency_ms: float):
        """Record a Redis operation."""
        labels = {'operation': operation, 'success': str(success).lower()}
        self._metrics.increment(self.REDIS_OPERATIONS, labels=labels)
        if success:
            self._metrics.record(self.REDIS_LATENCY, latency_ms, labels={'operation': operation})
        else:
            self._metrics.increment(self.REDIS_ERRORS, labels={'operation': operation})

    @contextmanager
    def measure_operation(self, operation_name: str):
        """Context manager to measure operation duration."""
        start = time.time()
        success = True
        try:
            yield
        except Exception:
            success = False
            raise
        finally:
            latency_ms = (time.time() - start) * 1000
            self.record_redis_operation(operation_name, success, latency_ms)

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all metrics."""
        snapshot = self._metrics.snapshot()

        return {
            'timestamp': snapshot.timestamp.isoformat(),
            'service': self._service_name,
            'counters': snapshot.counters,
            'gauges': snapshot.gauges,
            'histograms': {
                name: self._metrics.get_histogram_stats(name.split('{')[0])
                for name in snapshot.histograms.keys()
            }
        }

    def reset(self):
        """Reset all metrics."""
        self._metrics.reset()


_metrics: Optional[RalphMetrics] = None


def get_metrics() -> RalphMetrics:
    """Get the global metrics instance."""
    global _metrics
    if _metrics is None:
        _metrics = RalphMetrics()
    return _metrics


def init_metrics(service_name: str = 'ralph-client') -> RalphMetrics:
    """Initialize the global metrics instance."""
    global _metrics
    _metrics = RalphMetrics(service_name)
    return _metrics
