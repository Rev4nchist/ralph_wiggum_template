"""Hook Runner - Execute hooks at appropriate times"""

import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Dict, List, Optional, Any

from .config import HooksConfig, Hook, HookTrigger


@dataclass
class HookResult:
    """Result of hook execution."""
    hook_name: str
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    skipped: bool = False
    skip_reason: Optional[str] = None


class HookRunner:
    """Executes hooks at appropriate triggers."""

    def __init__(
        self,
        config_path: Optional[str] = None,
        agent_id: Optional[str] = None,
        redis_client: Optional[Any] = None
    ):
        self.config_path = config_path or "hooks.json"
        self.agent_id = agent_id or os.environ.get('RALPH_AGENT_ID', 'unknown')
        self.redis = redis_client
        self._config: Optional[HooksConfig] = None

    @property
    def config(self) -> HooksConfig:
        """Lazy-load hooks configuration."""
        if self._config is None:
            if Path(self.config_path).exists():
                self._config = HooksConfig.load(self.config_path)
            else:
                self._config = HooksConfig()
        return self._config

    def reload_config(self) -> None:
        """Force reload of hooks configuration."""
        self._config = None

    def run_hooks(
        self,
        trigger: HookTrigger,
        context: Optional[Dict[str, Any]] = None,
        file_path: Optional[str] = None
    ) -> List[HookResult]:
        """Run all hooks for a trigger."""
        context = context or {}
        results = []

        if file_path:
            hooks = self.config.get_hooks_for_file(file_path, trigger)
            context['FILE'] = file_path
        else:
            hooks = self.config.get_hooks_for_trigger(trigger)

        for hook in hooks:
            result = self._run_hook(hook, context)
            results.append(result)

            self._log_result(result)

            if hook.blocking and not result.success and hook.on_failure == "abort":
                break

        return results

    def _run_hook(self, hook: Hook, context: Dict[str, Any]) -> HookResult:
        """Execute a single hook."""
        if hook.condition:
            if not self._evaluate_condition(hook.condition, context):
                return HookResult(
                    hook_name=hook.name,
                    success=True,
                    exit_code=0,
                    stdout="",
                    stderr="",
                    duration_ms=0,
                    skipped=True,
                    skip_reason="Condition not met"
                )

        command = self._substitute_vars(hook.command, context)

        env = os.environ.copy()
        env.update(hook.env)
        env['RALPH_AGENT_ID'] = self.agent_id
        env['RALPH_HOOK_NAME'] = hook.name
        env['RALPH_HOOK_TRIGGER'] = hook.trigger

        start_time = time.time()

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=hook.timeout,
                env=env,
                cwd=os.getcwd()
            )

            duration_ms = int((time.time() - start_time) * 1000)

            return HookResult(
                hook_name=hook.name,
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_ms=duration_ms
            )

        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start_time) * 1000)
            return HookResult(
                hook_name=hook.name,
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"Hook timed out after {hook.timeout}s",
                duration_ms=duration_ms
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return HookResult(
                hook_name=hook.name,
                success=False,
                exit_code=-2,
                stdout="",
                stderr=str(e),
                duration_ms=duration_ms
            )

    def _substitute_vars(self, command: str, context: Dict[str, Any]) -> str:
        """Replace ${VAR} placeholders in command."""
        template = Template(command)
        return template.safe_substitute(context)

    def _evaluate_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """Evaluate hook condition."""
        try:
            return eval(condition, {"__builtins__": {}}, context)
        except Exception:
            return True

    def _log_result(self, result: HookResult) -> None:
        """Log hook result to Redis if available."""
        if self.redis:
            log_entry = {
                'agent_id': self.agent_id,
                'hook_name': result.hook_name,
                'success': result.success,
                'exit_code': result.exit_code,
                'duration_ms': result.duration_ms,
                'skipped': result.skipped,
                'timestamp': datetime.utcnow().isoformat()
            }

            self.redis.rpush(
                f"ralph:hooks:log:{self.agent_id}",
                json.dumps(log_entry)
            )

            self.redis.ltrim(f"ralph:hooks:log:{self.agent_id}", -100, -1)

    def pre_commit(self, files: Optional[List[str]] = None) -> bool:
        """Run pre-commit hooks. Returns True if all pass."""
        context = {'FILES': files or []}
        results = self.run_hooks(HookTrigger.PRE_COMMIT, context)

        return all(r.success or r.skipped for r in results)

    def post_commit(self, commit_sha: str) -> List[HookResult]:
        """Run post-commit hooks."""
        context = {'COMMIT_SHA': commit_sha}
        return self.run_hooks(HookTrigger.POST_COMMIT, context)

    def pre_edit(self, file_path: str) -> bool:
        """Run pre-edit hooks for a file. Returns True if edit allowed."""
        results = self.run_hooks(HookTrigger.PRE_EDIT, file_path=file_path)
        return all(r.success or r.skipped for r in results)

    def post_edit(self, file_path: str) -> List[HookResult]:
        """Run post-edit hooks for a file."""
        return self.run_hooks(HookTrigger.POST_EDIT, file_path=file_path)

    def pre_task(self, task_id: str, task_type: str) -> bool:
        """Run pre-task hooks. Returns True if task can proceed."""
        context = {'TASK_ID': task_id, 'TASK_TYPE': task_type}
        results = self.run_hooks(HookTrigger.PRE_TASK, context)
        return all(r.success or r.skipped for r in results)

    def post_task(self, task_id: str, task_type: str, success: bool) -> List[HookResult]:
        """Run post-task hooks."""
        context = {
            'TASK_ID': task_id,
            'TASK_TYPE': task_type,
            'TASK_SUCCESS': success
        }

        trigger = HookTrigger.TASK_COMPLETE if success else HookTrigger.TASK_FAIL
        return self.run_hooks(trigger, context)

    def on_error(self, error: str, context: Optional[Dict] = None) -> List[HookResult]:
        """Run error hooks."""
        ctx = context or {}
        ctx['ERROR'] = error
        return self.run_hooks(HookTrigger.ON_ERROR, ctx)
