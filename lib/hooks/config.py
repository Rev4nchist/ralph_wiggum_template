"""Hooks Configuration - Schema and loading"""

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any


class HookTrigger(Enum):
    PRE_COMMIT = "pre-commit"
    POST_COMMIT = "post-commit"
    PRE_EDIT = "pre-edit"
    POST_EDIT = "post-edit"
    PRE_TASK = "pre-task"
    POST_TASK = "post-task"
    TASK_COMPLETE = "task-complete"
    TASK_FAIL = "task-fail"
    ON_ERROR = "on-error"
    PRE_BUILD = "pre-build"
    POST_BUILD = "post-build"
    PRE_TEST = "pre-test"
    POST_TEST = "post-test"


@dataclass
class Hook:
    """Single hook definition."""
    name: str
    trigger: str
    command: str
    description: str = ""
    enabled: bool = True
    blocking: bool = True
    timeout: int = 60
    file_patterns: List[str] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    on_failure: str = "abort"
    condition: Optional[str] = None

    def matches_file(self, file_path: str) -> bool:
        """Check if hook applies to given file."""
        if not self.file_patterns:
            return True

        from fnmatch import fnmatch
        path = Path(file_path)

        for pattern in self.exclude_patterns:
            if fnmatch(str(path), pattern) or fnmatch(path.name, pattern):
                return False

        for pattern in self.file_patterns:
            if fnmatch(str(path), pattern) or fnmatch(path.name, pattern):
                return True

        return False


@dataclass
class HooksConfig:
    """Complete hooks configuration."""
    version: str = "1.0"
    hooks: List[Hook] = field(default_factory=list)
    globals: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str) -> 'HooksConfig':
        """Load hooks config from JSON file."""
        with open(path, 'r') as f:
            data = json.load(f)

        hooks = [
            Hook(**h) for h in data.get('hooks', [])
        ]

        return cls(
            version=data.get('version', '1.0'),
            hooks=hooks,
            globals=data.get('globals', {})
        )

    def get_hooks_for_trigger(self, trigger: HookTrigger) -> List[Hook]:
        """Get all enabled hooks for a specific trigger."""
        return [
            h for h in self.hooks
            if h.enabled and h.trigger == trigger.value
        ]

    def get_hooks_for_file(self, file_path: str, trigger: HookTrigger) -> List[Hook]:
        """Get hooks that apply to a specific file and trigger."""
        return [
            h for h in self.get_hooks_for_trigger(trigger)
            if h.matches_file(file_path)
        ]


def create_default_config() -> Dict:
    """Create default hooks.json content."""
    return {
        "version": "1.0",
        "globals": {
            "timeout_default": 60,
            "continue_on_warning": True
        },
        "hooks": [
            {
                "name": "security-scan",
                "trigger": "pre-commit",
                "command": "python -m lib.hooks.builtin.security_scan",
                "description": "Scan for secrets and vulnerabilities",
                "enabled": True,
                "blocking": True,
                "timeout": 30,
                "on_failure": "abort"
            },
            {
                "name": "file-protection",
                "trigger": "pre-edit",
                "command": "python -m lib.hooks.builtin.file_protection ${FILE}",
                "description": "Check file lock before editing",
                "enabled": True,
                "blocking": True,
                "timeout": 5,
                "on_failure": "abort"
            },
            {
                "name": "auto-format",
                "trigger": "post-edit",
                "command": "npx prettier --write ${FILE}",
                "description": "Format code after editing",
                "enabled": True,
                "blocking": False,
                "timeout": 10,
                "file_patterns": ["*.ts", "*.tsx", "*.js", "*.jsx", "*.json"],
                "on_failure": "warn"
            },
            {
                "name": "lint-check",
                "trigger": "pre-commit",
                "command": "npm run lint -- --fix",
                "description": "Run linter before commit",
                "enabled": True,
                "blocking": True,
                "timeout": 60,
                "on_failure": "abort"
            },
            {
                "name": "type-check",
                "trigger": "pre-commit",
                "command": "npm run typecheck",
                "description": "TypeScript type checking",
                "enabled": True,
                "blocking": True,
                "timeout": 120,
                "file_patterns": ["*.ts", "*.tsx"],
                "on_failure": "abort"
            },
            {
                "name": "test-affected",
                "trigger": "task-complete",
                "command": "npm test -- --changedSince=HEAD~1",
                "description": "Run tests for affected files",
                "enabled": True,
                "blocking": True,
                "timeout": 300,
                "on_failure": "warn"
            },
            {
                "name": "build-verify",
                "trigger": "task-complete",
                "command": "npm run build",
                "description": "Verify build succeeds",
                "enabled": True,
                "blocking": True,
                "timeout": 180,
                "on_failure": "abort"
            }
        ]
    }
