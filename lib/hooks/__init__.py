"""Ralph Wiggum Hooks System

Automation hooks for pre/post task operations.
"""

from .runner import HookRunner
from .config import HooksConfig, Hook, HookTrigger

__all__ = [
    'HookRunner',
    'HooksConfig',
    'Hook',
    'HookTrigger'
]
