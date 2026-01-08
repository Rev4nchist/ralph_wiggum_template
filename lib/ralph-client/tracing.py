"""Distributed tracing for Ralph multi-agent platform."""
import uuid
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from contextlib import contextmanager


@dataclass
class Span:
    """A single span in a trace."""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    operation_name: str
    service_name: str
    start_time: float
    end_time: Optional[float] = None
    status: str = 'ok'
    tags: Dict[str, str] = field(default_factory=dict)
    logs: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def duration_ms(self) -> Optional[float]:
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000

    def set_tag(self, key: str, value: str):
        self.tags[key] = value

    def log(self, message: str, **kwargs):
        self.logs.append({
            'timestamp': time.time(),
            'message': message,
            **kwargs
        })

    def finish(self, status: str = 'ok'):
        self.end_time = time.time()
        self.status = status

    def to_dict(self) -> Dict[str, Any]:
        return {
            'trace_id': self.trace_id,
            'span_id': self.span_id,
            'parent_span_id': self.parent_span_id,
            'operation_name': self.operation_name,
            'service_name': self.service_name,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'duration_ms': self.duration_ms,
            'status': self.status,
            'tags': self.tags,
            'logs': self.logs
        }


class TraceContext:
    """Thread-local trace context."""

    def __init__(self):
        self._trace_id: Optional[str] = None
        self._span_stack: List[Span] = []

    @property
    def trace_id(self) -> Optional[str]:
        return self._trace_id

    @property
    def current_span(self) -> Optional[Span]:
        return self._span_stack[-1] if self._span_stack else None

    def start_trace(self, trace_id: Optional[str] = None) -> str:
        self._trace_id = trace_id or str(uuid.uuid4())
        self._span_stack = []
        return self._trace_id

    def end_trace(self):
        self._trace_id = None
        self._span_stack = []

    def push_span(self, span: Span):
        self._span_stack.append(span)

    def pop_span(self) -> Optional[Span]:
        return self._span_stack.pop() if self._span_stack else None


class Tracer:
    """Distributed tracer for Ralph platform."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self._context = TraceContext()
        self._spans: List[Span] = []
        self._max_spans = 1000

    def start_span(self, operation_name: str, trace_id: Optional[str] = None) -> Span:
        """Start a new span."""
        if trace_id:
            self._context.start_trace(trace_id)
        elif not self._context.trace_id:
            self._context.start_trace()

        parent_span = self._context.current_span
        parent_span_id = parent_span.span_id if parent_span else None

        span = Span(
            trace_id=self._context.trace_id,
            span_id=str(uuid.uuid4())[:8],
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            service_name=self.service_name,
            start_time=time.time()
        )

        self._context.push_span(span)
        return span

    def finish_span(self, span: Span, status: str = 'ok'):
        """Finish a span and record it."""
        span.finish(status)
        self._context.pop_span()

        self._spans.append(span)
        if len(self._spans) > self._max_spans:
            self._spans = self._spans[-self._max_spans:]

    @contextmanager
    def trace(self, operation_name: str, trace_id: Optional[str] = None):
        """Context manager for tracing an operation."""
        span = self.start_span(operation_name, trace_id)
        try:
            yield span
            self.finish_span(span, 'ok')
        except Exception as e:
            span.set_tag('error', str(e))
            span.log('error', error=str(e), error_type=type(e).__name__)
            self.finish_span(span, 'error')
            raise

    def get_trace(self, trace_id: str) -> List[Span]:
        """Get all spans for a trace."""
        return [s for s in self._spans if s.trace_id == trace_id]

    def get_recent_spans(self, limit: int = 100) -> List[Span]:
        """Get most recent spans."""
        return self._spans[-limit:]

    def inject_context(self) -> Dict[str, str]:
        """Get trace context for propagation to other services."""
        if not self._context.trace_id:
            return {}

        current = self._context.current_span
        return {
            'trace_id': self._context.trace_id,
            'span_id': current.span_id if current else '',
            'service': self.service_name
        }

    def extract_context(self, headers: Dict[str, str]) -> Optional[str]:
        """Extract trace context from incoming headers."""
        return headers.get('trace_id')


class TaskTracer(Tracer):
    """Tracer with task-specific helpers."""

    def trace_claim(self, task_id: str, agent_id: str, trace_id: Optional[str] = None):
        """Trace a task claim operation."""
        return self.trace('task.claim', trace_id)

    def trace_execute(self, task_id: str, agent_id: str, trace_id: Optional[str] = None):
        """Trace task execution."""
        return self.trace('task.execute', trace_id)

    def trace_complete(self, task_id: str, agent_id: str, trace_id: Optional[str] = None):
        """Trace task completion."""
        return self.trace('task.complete', trace_id)


_tracer: Optional[TaskTracer] = None


def get_tracer() -> TaskTracer:
    """Get the global tracer instance."""
    global _tracer
    if _tracer is None:
        _tracer = TaskTracer('ralph-client')
    return _tracer


def init_tracer(service_name: str = 'ralph-client') -> TaskTracer:
    """Initialize the global tracer."""
    global _tracer
    _tracer = TaskTracer(service_name)
    return _tracer
