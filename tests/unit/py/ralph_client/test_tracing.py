"""Tests for distributed tracing module."""

import time
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "lib" / "ralph-client"))

from tracing import (
    Span,
    TraceContext,
    Tracer,
    TaskTracer,
    get_tracer,
    init_tracer,
)


class TestSpan:
    """Tests for the Span class."""

    def test_span_creation(self):
        """Span initializes with required fields."""
        span = Span(
            trace_id='trace-123',
            span_id='span-456',
            parent_span_id=None,
            operation_name='test.op',
            service_name='test-service',
            start_time=time.time()
        )

        assert span.trace_id == 'trace-123'
        assert span.span_id == 'span-456'
        assert span.parent_span_id is None
        assert span.operation_name == 'test.op'
        assert span.service_name == 'test-service'
        assert span.status == 'ok'
        assert span.end_time is None

    def test_duration_before_finish(self):
        """Duration is None before finish."""
        span = Span(
            trace_id='t', span_id='s', parent_span_id=None,
            operation_name='op', service_name='svc',
            start_time=time.time()
        )
        assert span.duration_ms is None

    def test_duration_after_finish(self):
        """Duration is calculated after finish."""
        start = time.time()
        span = Span(
            trace_id='t', span_id='s', parent_span_id=None,
            operation_name='op', service_name='svc',
            start_time=start
        )
        time.sleep(0.01)
        span.finish()

        assert span.duration_ms is not None
        assert span.duration_ms >= 10

    def test_set_tag(self):
        """Tags can be set on span."""
        span = Span(
            trace_id='t', span_id='s', parent_span_id=None,
            operation_name='op', service_name='svc',
            start_time=time.time()
        )

        span.set_tag('key', 'value')
        assert span.tags['key'] == 'value'

    def test_log(self):
        """Logs can be added to span."""
        span = Span(
            trace_id='t', span_id='s', parent_span_id=None,
            operation_name='op', service_name='svc',
            start_time=time.time()
        )

        span.log('test message', extra='data')

        assert len(span.logs) == 1
        assert span.logs[0]['message'] == 'test message'
        assert span.logs[0]['extra'] == 'data'
        assert 'timestamp' in span.logs[0]

    def test_finish_sets_status(self):
        """Finish sets status and end time."""
        span = Span(
            trace_id='t', span_id='s', parent_span_id=None,
            operation_name='op', service_name='svc',
            start_time=time.time()
        )

        span.finish('error')

        assert span.status == 'error'
        assert span.end_time is not None

    def test_to_dict(self):
        """to_dict returns all span data."""
        span = Span(
            trace_id='trace-123', span_id='span-456', parent_span_id='span-parent',
            operation_name='test.op', service_name='test-service',
            start_time=1000.0
        )
        span.set_tag('env', 'test')
        span.log('test log')
        span.finish('ok')

        d = span.to_dict()

        assert d['trace_id'] == 'trace-123'
        assert d['span_id'] == 'span-456'
        assert d['parent_span_id'] == 'span-parent'
        assert d['operation_name'] == 'test.op'
        assert d['service_name'] == 'test-service'
        assert d['start_time'] == 1000.0
        assert d['end_time'] is not None
        assert d['status'] == 'ok'
        assert d['tags'] == {'env': 'test'}
        assert len(d['logs']) == 1


class TestTraceContext:
    """Tests for TraceContext class."""

    def test_initial_state(self):
        """Context starts empty."""
        ctx = TraceContext()
        assert ctx.trace_id is None
        assert ctx.current_span is None

    def test_start_trace_generates_id(self):
        """start_trace generates trace ID."""
        ctx = TraceContext()
        trace_id = ctx.start_trace()

        assert trace_id is not None
        assert ctx.trace_id == trace_id

    def test_start_trace_with_id(self):
        """start_trace accepts existing ID."""
        ctx = TraceContext()
        trace_id = ctx.start_trace('custom-trace-id')

        assert trace_id == 'custom-trace-id'
        assert ctx.trace_id == 'custom-trace-id'

    def test_end_trace(self):
        """end_trace clears context."""
        ctx = TraceContext()
        ctx.start_trace()
        ctx.end_trace()

        assert ctx.trace_id is None
        assert ctx.current_span is None

    def test_push_pop_span(self):
        """Spans can be pushed and popped."""
        ctx = TraceContext()
        span1 = Span('t', 's1', None, 'op1', 'svc', time.time())
        span2 = Span('t', 's2', 's1', 'op2', 'svc', time.time())

        ctx.push_span(span1)
        assert ctx.current_span is span1

        ctx.push_span(span2)
        assert ctx.current_span is span2

        popped = ctx.pop_span()
        assert popped is span2
        assert ctx.current_span is span1

    def test_pop_empty_returns_none(self):
        """Popping empty stack returns None."""
        ctx = TraceContext()
        assert ctx.pop_span() is None


class TestTracer:
    """Tests for Tracer class."""

    @pytest.fixture
    def tracer(self):
        return Tracer('test-service')

    def test_start_span_creates_trace(self, tracer):
        """start_span creates trace if none exists."""
        span = tracer.start_span('test.op')

        assert span.trace_id is not None
        assert span.operation_name == 'test.op'
        assert span.service_name == 'test-service'

    def test_start_span_with_trace_id(self, tracer):
        """start_span uses provided trace ID."""
        span = tracer.start_span('test.op', trace_id='custom-id')
        assert span.trace_id == 'custom-id'

    def test_nested_spans_have_parent(self, tracer):
        """Nested spans have parent span ID."""
        parent = tracer.start_span('parent.op')
        child = tracer.start_span('child.op')

        assert child.parent_span_id == parent.span_id
        assert child.trace_id == parent.trace_id

    def test_finish_span_records(self, tracer):
        """finish_span records the span."""
        span = tracer.start_span('test.op')
        tracer.finish_span(span)

        recent = tracer.get_recent_spans(1)
        assert len(recent) == 1
        assert recent[0].operation_name == 'test.op'

    def test_trace_context_manager(self, tracer):
        """trace context manager handles span lifecycle."""
        with tracer.trace('context.op') as span:
            span.set_tag('test', 'value')

        recent = tracer.get_recent_spans(1)
        assert len(recent) == 1
        assert recent[0].status == 'ok'
        assert recent[0].tags['test'] == 'value'

    def test_trace_context_manager_error(self, tracer):
        """trace context manager records error."""
        with pytest.raises(ValueError):
            with tracer.trace('failing.op') as span:
                raise ValueError("test error")

        recent = tracer.get_recent_spans(1)
        assert recent[0].status == 'error'
        assert 'error' in recent[0].tags

    def test_get_trace(self, tracer):
        """get_trace returns all spans for a trace."""
        trace_id = None
        with tracer.trace('op1') as span1:
            trace_id = span1.trace_id
            with tracer.trace('op2'):
                pass

        spans = tracer.get_trace(trace_id)
        assert len(spans) == 2

    def test_max_spans_limit(self, tracer):
        """Tracer limits stored spans."""
        tracer._max_spans = 10

        for i in range(20):
            span = tracer.start_span(f'op-{i}')
            tracer.finish_span(span)

        assert len(tracer._spans) == 10

    def test_inject_context(self, tracer):
        """inject_context returns trace headers."""
        with tracer.trace('test.op') as span:
            ctx = tracer.inject_context()

            assert ctx['trace_id'] == span.trace_id
            assert ctx['span_id'] == span.span_id
            assert ctx['service'] == 'test-service'

    def test_inject_context_empty(self, tracer):
        """inject_context returns empty when no trace."""
        ctx = tracer.inject_context()
        assert ctx == {}

    def test_extract_context(self, tracer):
        """extract_context gets trace ID from headers."""
        headers = {'trace_id': 'incoming-trace'}
        trace_id = tracer.extract_context(headers)
        assert trace_id == 'incoming-trace'


class TestTaskTracer:
    """Tests for TaskTracer class."""

    @pytest.fixture
    def tracer(self):
        return TaskTracer('test-service')

    def test_trace_claim(self, tracer):
        """trace_claim creates claim span."""
        with tracer.trace_claim('task-1', 'agent-1') as span:
            pass

        recent = tracer.get_recent_spans(1)
        assert recent[0].operation_name == 'task.claim'

    def test_trace_execute(self, tracer):
        """trace_execute creates execute span."""
        with tracer.trace_execute('task-1', 'agent-1') as span:
            pass

        recent = tracer.get_recent_spans(1)
        assert recent[0].operation_name == 'task.execute'

    def test_trace_complete(self, tracer):
        """trace_complete creates complete span."""
        with tracer.trace_complete('task-1', 'agent-1') as span:
            pass

        recent = tracer.get_recent_spans(1)
        assert recent[0].operation_name == 'task.complete'

    def test_task_workflow_tracing(self, tracer):
        """Full task workflow is traceable."""
        with tracer.trace_claim('task-1', 'agent-1', trace_id='workflow-1'):
            pass
        with tracer.trace_execute('task-1', 'agent-1', trace_id='workflow-1'):
            pass
        with tracer.trace_complete('task-1', 'agent-1', trace_id='workflow-1'):
            pass

        spans = tracer.get_trace('workflow-1')
        assert len(spans) == 3
        ops = [s.operation_name for s in spans]
        assert 'task.claim' in ops
        assert 'task.execute' in ops
        assert 'task.complete' in ops


class TestGlobalTracer:
    """Tests for global tracer functions."""

    def test_get_tracer_creates_instance(self):
        """get_tracer creates instance if none exists."""
        import tracing
        tracing._tracer = None

        t = get_tracer()
        assert t is not None
        assert isinstance(t, TaskTracer)

    def test_get_tracer_returns_same_instance(self):
        """get_tracer returns same instance."""
        t1 = get_tracer()
        t2 = get_tracer()
        assert t1 is t2

    def test_init_tracer_creates_new_instance(self):
        """init_tracer creates new instance with service name."""
        t = init_tracer('custom-service')
        assert t.service_name == 'custom-service'

    def test_init_tracer_replaces_global(self):
        """init_tracer replaces global instance."""
        t1 = get_tracer()
        t2 = init_tracer('new-service')
        t3 = get_tracer()

        assert t3 is t2
        assert t3 is not t1
