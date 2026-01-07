"""Ralph Wiggum Agent Client Library

Redis-based coordination for multi-agent orchestration.
"""

from .client import RalphClient
from .locks import FileLock
from .tasks import TaskQueue, Task, TaskStatus
from .registry import AgentRegistry

__all__ = [
    'RalphClient',
    'FileLock',
    'TaskQueue',
    'Task',
    'TaskStatus',
    'AgentRegistry'
]

__version__ = '0.1.0'
