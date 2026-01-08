"""Tests for telemetry and metrics module."""

import time
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "lib" / "ralph-client"))

from telemetry import (
    SimpleMetrics,
    RalphMetrics,
    MetricSnapshot,
    get_metrics,
    init_metrics,
)


class TestSimpleMetrics:
    """Tests for the SimpleMetrics class."""

    @pytest.fixture
    def metrics(self):
        return SimpleMetrics()

    def test_increment_counter(self, metrics):
        """Counter increments correctly."""
        metrics.increment('test.counter')
        assert metrics.get_counter('test.counter') == 1

        metrics.increment('test.counter', 5)
        assert metrics.get_counter('test.counter') == 6

    def test_increment_with_labels(self, metrics):
        """Counter with labels tracks separately."""
        metrics.increment('test.counter', labels={'env': 'prod'})
        metrics.increment('test.counter', labels={'env': 'dev'})
        metrics.increment('test.counter', labels={'env': 'prod'})

        assert metrics.get_counter('test.counter', labels={'env': 'prod'}) == 2
        assert metrics.get_counter('test.counter', labels={'env': 'dev'}) == 1

    def test_record_histogram(self, metrics):
        """Histogram records values."""
        for v in [10, 20, 30, 40, 50]:
            metrics.record('test.latency', v)

        stats = metrics.get_histogram_stats('test.latency')
        assert stats['count'] == 5
        assert stats['min'] == 10
        assert stats['max'] == 50
        assert stats['avg'] == 30

    def test_histogram_empty_stats(self, metrics):
        """Empty histogram returns zero stats."""
        stats = metrics.get_histogram_stats('nonexistent')
        assert stats['count'] == 0
        assert stats['min'] == 0
        assert stats['max'] == 0

    def test_histogram_percentiles(self, metrics):
        """Histogram calculates percentiles."""
        for i in range(100):
            metrics.record('test.dist', i)

        stats = metrics.get_histogram_stats('test.dist')
        assert stats['p50'] == 50
        assert stats['p95'] >= 94
        assert stats['p99'] >= 98

    def test_histogram_caps_at_1000(self, metrics):
        """Histogram caps at 1000 values."""
        for i in range(1500):
            metrics.record('test.capped', i)

        stats = metrics.get_histogram_stats('test.capped')
        assert stats['count'] == 1000
        assert stats['min'] == 500

    def test_set_gauge(self, metrics):
        """Gauge sets and overwrites value."""
        metrics.set_gauge('test.gauge', 100)
        snapshot = metrics.snapshot()
        assert snapshot.gauges['test.gauge'] == 100

        metrics.set_gauge('test.gauge', 200)
        snapshot = metrics.snapshot()
        assert snapshot.gauges['test.gauge'] == 200

    def test_snapshot(self, metrics):
        """Snapshot captures all metrics."""
        metrics.increment('counter')
        metrics.record('hist', 42)
        metrics.set_gauge('gauge', 3.14)

        snap = metrics.snapshot()

        assert isinstance(snap, MetricSnapshot)
        assert snap.counters['counter'] == 1
        assert 42 in snap.histograms['hist']
        assert snap.gauges['gauge'] == 3.14
        assert snap.timestamp is not None

    def test_reset(self, metrics):
        """Reset clears all metrics."""
        metrics.increment('counter')
        metrics.record('hist', 1)
        metrics.set_gauge('gauge', 1)

        metrics.reset()
        snap = metrics.snapshot()

        assert len(snap.counters) == 0
        assert len(snap.histograms) == 0
        assert len(snap.gauges) == 0

    def test_make_key_with_labels(self, metrics):
        """Labels create unique keys."""
        key1 = metrics._make_key('metric', {'a': '1', 'b': '2'})
        key2 = metrics._make_key('metric', {'b': '2', 'a': '1'})
        key3 = metrics._make_key('metric', {'a': '1'})
        key4 = metrics._make_key('metric')

        assert key1 == key2
        assert key1 != key3
        assert key3 != key4
        assert 'metric{' in key1


class TestRalphMetrics:
    """Tests for RalphMetrics class."""

    @pytest.fixture
    def metrics(self):
        return RalphMetrics('test-service')

    def test_record_claim_success(self, metrics):
        """Records successful task claim."""
        metrics.record_claim('agent-1', 'task-1', True, 50.0)

        summary = metrics.get_summary()
        assert 'ralph.tasks.claims{agent_id=agent-1,success=true}' in summary['counters']

    def test_record_claim_failure(self, metrics):
        """Records failed task claim."""
        metrics.record_claim('agent-1', 'task-1', False, 0)

        summary = metrics.get_summary()
        assert 'ralph.tasks.claims{agent_id=agent-1,success=false}' in summary['counters']

    def test_record_completion(self, metrics):
        """Records task completion."""
        metrics.record_completion('agent-1', 'task-1', 1500.0)

        summary = metrics.get_summary()
        assert 'ralph.tasks.completions{agent_id=agent-1}' in summary['counters']

    def test_record_failure(self, metrics):
        """Records task failure."""
        metrics.record_failure('agent-1', 'task-1', 'timeout')

        summary = metrics.get_summary()
        assert 'ralph.tasks.failures{agent_id=agent-1,error_type=timeout}' in summary['counters']

    def test_record_lock_acquired(self, metrics):
        """Records lock acquisition."""
        metrics.record_lock_acquired('agent-1', '/file.py', 100)

        summary = metrics.get_summary()
        assert 'ralph.locks.acquisitions{agent_id=agent-1}' in summary['counters']

    def test_record_lock_released(self, metrics):
        """Records lock release."""
        metrics.record_lock_released('agent-1', '/file.py')

        summary = metrics.get_summary()
        assert 'ralph.locks.releases{agent_id=agent-1}' in summary['counters']

    def test_record_lock_contention(self, metrics):
        """Records lock contention."""
        metrics.record_lock_contention('agent-1', '/file.py', 'agent-2')

        summary = metrics.get_summary()
        assert 'ralph.locks.contentions{agent_id=agent-1,holder=agent-2}' in summary['counters']

    def test_record_registration(self, metrics):
        """Records agent registration."""
        metrics.record_registration('agent-1', 'implementer')

        summary = metrics.get_summary()
        assert 'ralph.agents.registrations{agent_type=implementer}' in summary['counters']

    def test_record_heartbeat(self, metrics):
        """Records agent heartbeat."""
        metrics.record_heartbeat('agent-1')

        summary = metrics.get_summary()
        assert 'ralph.agents.heartbeats{agent_id=agent-1}' in summary['counters']

    def test_set_active_agents(self, metrics):
        """Sets active agent count gauge."""
        metrics.set_active_agents(5)

        summary = metrics.get_summary()
        assert summary['gauges']['ralph.agents.active'] == 5

    def test_record_redis_operation_success(self, metrics):
        """Records successful Redis operation."""
        metrics.record_redis_operation('GET', True, 2.5)

        summary = metrics.get_summary()
        assert 'ralph.redis.operations{operation=GET,success=true}' in summary['counters']

    def test_record_redis_operation_failure(self, metrics):
        """Records failed Redis operation."""
        metrics.record_redis_operation('SET', False, 0)

        summary = metrics.get_summary()
        assert 'ralph.redis.operations{operation=SET,success=false}' in summary['counters']
        assert 'ralph.redis.errors{operation=SET}' in summary['counters']

    def test_measure_operation_context_manager(self, metrics):
        """Measure operation context manager records latency."""
        with metrics.measure_operation('test_op'):
            time.sleep(0.01)

        summary = metrics.get_summary()
        assert 'ralph.redis.operations{operation=test_op,success=true}' in summary['counters']

    def test_measure_operation_exception(self, metrics):
        """Measure operation records failure on exception."""
        with pytest.raises(ValueError):
            with metrics.measure_operation('failing_op'):
                raise ValueError("test error")

        summary = metrics.get_summary()
        assert 'ralph.redis.operations{operation=failing_op,success=false}' in summary['counters']

    def test_get_summary_structure(self, metrics):
        """Summary has expected structure."""
        metrics.record_claim('agent-1', 'task-1', True, 50)

        summary = metrics.get_summary()

        assert 'timestamp' in summary
        assert 'service' in summary
        assert summary['service'] == 'test-service'
        assert 'counters' in summary
        assert 'gauges' in summary
        assert 'histograms' in summary

    def test_reset(self, metrics):
        """Reset clears all metrics."""
        metrics.record_claim('agent-1', 'task-1', True, 50)
        metrics.reset()

        summary = metrics.get_summary()
        assert len(summary['counters']) == 0


class TestGlobalMetrics:
    """Tests for global metrics functions."""

    def test_get_metrics_creates_instance(self):
        """get_metrics creates instance if none exists."""
        import telemetry
        telemetry._metrics = None

        m = get_metrics()
        assert m is not None
        assert isinstance(m, RalphMetrics)

    def test_get_metrics_returns_same_instance(self):
        """get_metrics returns same instance."""
        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2

    def test_init_metrics_creates_new_instance(self):
        """init_metrics creates new instance with service name."""
        m = init_metrics('custom-service')

        summary = m.get_summary()
        assert summary['service'] == 'custom-service'

    def test_init_metrics_replaces_global(self):
        """init_metrics replaces global instance."""
        m1 = get_metrics()
        m2 = init_metrics('new-service')
        m3 = get_metrics()

        assert m3 is m2
        assert m3 is not m1
