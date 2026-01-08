"""Ralph Wiggum Agent Client Library

Redis-based coordination for multi-agent orchestration.
"""

from .client import RalphClient
from .locks import FileLock
from .tasks import TaskQueue, Task, TaskStatus
from .registry import AgentRegistry
from .auth import TokenAuth, AuthLevel, AuthError, AgentCredentials, require_auth
from .security import (
    sanitize,
    sanitize_dict,
    is_sensitive,
    mask_partially,
    SecureLogger,
    SanitizedException,
    REDACTED,
)
from .cleanup import OrphanCleaner, OrphanedTask
from .streams import EventStream, StreamMessage
from .constants import RedisKeys, TaskStatusConst, TaskTypeConst, Defaults
from .telemetry import RalphMetrics, SimpleMetrics, MetricSnapshot, get_metrics, init_metrics
from .tracing import Tracer, TaskTracer, Span, TraceContext, get_tracer, init_tracer

__all__ = [
    'RalphClient',
    'FileLock',
    'TaskQueue',
    'Task',
    'TaskStatus',
    'AgentRegistry',
    'TokenAuth',
    'AuthLevel',
    'AuthError',
    'AgentCredentials',
    'require_auth',
    'sanitize',
    'sanitize_dict',
    'is_sensitive',
    'mask_partially',
    'SecureLogger',
    'SanitizedException',
    'REDACTED',
    'OrphanCleaner',
    'OrphanedTask',
    'EventStream',
    'StreamMessage',
    'RedisKeys',
    'TaskStatusConst',
    'TaskTypeConst',
    'Defaults',
    'RalphMetrics',
    'SimpleMetrics',
    'MetricSnapshot',
    'get_metrics',
    'init_metrics',
    'Tracer',
    'TaskTracer',
    'Span',
    'TraceContext',
    'get_tracer',
    'init_tracer',
]

__version__ = '0.1.0'
