"""Tests for Hook Runner - Comprehensive coverage of hook execution system."""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from lib.hooks.config import Hook, HooksConfig, HookTrigger
from lib.hooks.runner import HookRunner, HookResult


class TestHookResult:
    """Tests for HookResult dataclass."""

    def test_create_successful_result(self):
        result = HookResult(
            hook_name="test-hook",
            success=True,
            exit_code=0,
            stdout="output",
            stderr="",
            duration_ms=100
        )
        assert result.hook_name == "test-hook"
        assert result.success is True
        assert result.exit_code == 0
        assert result.skipped is False

    def test_create_skipped_result(self):
        result = HookResult(
            hook_name="test-hook",
            success=True,
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=0,
            skipped=True,
            skip_reason="Condition not met"
        )
        assert result.skipped is True
        assert result.skip_reason == "Condition not met"


class TestHookRunner:
    """Tests for HookRunner class."""

    @pytest.fixture
    def runner(self):
        return HookRunner(config_path="nonexistent.json", agent_id="test-agent")

    @pytest.fixture
    def mock_redis(self):
        redis = MagicMock()
        return redis

    @pytest.fixture
    def runner_with_redis(self, mock_redis):
        return HookRunner(
            config_path="nonexistent.json",
            agent_id="test-agent",
            redis_client=mock_redis
        )

    def test_init_defaults(self):
        runner = HookRunner()
        assert runner.config_path == "hooks.json"
        assert runner._config is None

    def test_init_with_custom_path(self):
        runner = HookRunner(config_path="custom.json", agent_id="agent-1")
        assert runner.config_path == "custom.json"
        assert runner.agent_id == "agent-1"

    def test_config_lazy_loading_missing_file(self, runner):
        config = runner.config
        assert isinstance(config, HooksConfig)
        assert len(config.hooks) == 0

    def test_config_lazy_loading_existing_file(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        try:
            json.dump({
                "version": "1.0",
                "hooks": [{
                    "name": "test",
                    "trigger": "pre-commit",
                    "command": "echo test"
                }]
            }, f)
            f.close()

            runner = HookRunner(config_path=f.name)
            config = runner.config
            assert len(config.hooks) == 1
            assert config.hooks[0].name == "test"
        finally:
            try:
                os.unlink(f.name)
            except PermissionError:
                pass

    def test_reload_config(self, runner):
        _ = runner.config
        runner._config = HooksConfig(hooks=[Hook(name="old", trigger="pre-commit", command="old")])
        runner.reload_config()
        assert runner._config is None


class TestRunHooks:
    """Tests for run_hooks method."""

    @pytest.fixture
    def runner_with_config(self):
        runner = HookRunner(agent_id="test-agent")
        runner._config = HooksConfig(hooks=[
            Hook(name="hook1", trigger="pre-commit", command="echo hook1"),
            Hook(name="hook2", trigger="pre-commit", command="echo hook2"),
            Hook(name="hook3", trigger="post-commit", command="echo hook3")
        ])
        return runner

    @patch('lib.hooks.runner.subprocess.run')
    def test_run_hooks_filters_by_trigger(self, mock_run, runner_with_config):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

        results = runner_with_config.run_hooks(HookTrigger.PRE_COMMIT)

        assert len(results) == 2
        assert mock_run.call_count == 2

    @patch('lib.hooks.runner.subprocess.run')
    def test_run_hooks_execution_order(self, mock_run, runner_with_config):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

        results = runner_with_config.run_hooks(HookTrigger.PRE_COMMIT)

        assert results[0].hook_name == "hook1"
        assert results[1].hook_name == "hook2"

    @patch('lib.hooks.runner.subprocess.run')
    def test_run_hooks_with_file_path(self, mock_run):
        runner = HookRunner(agent_id="test-agent")
        runner._config = HooksConfig(hooks=[
            Hook(name="ts-hook", trigger="pre-edit", command="echo ts", file_patterns=["*.ts"]),
            Hook(name="all-hook", trigger="pre-edit", command="echo all")
        ])
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

        results = runner.run_hooks(HookTrigger.PRE_EDIT, file_path="test.ts")

        assert len(results) == 2

    @patch('lib.hooks.runner.subprocess.run')
    def test_run_hooks_blocking_aborts_on_failure(self, mock_run):
        runner = HookRunner(agent_id="test-agent")
        runner._config = HooksConfig(hooks=[
            Hook(name="failing", trigger="pre-commit", command="exit 1", blocking=True, on_failure="abort"),
            Hook(name="never-runs", trigger="pre-commit", command="echo never")
        ])
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")

        results = runner.run_hooks(HookTrigger.PRE_COMMIT)

        assert len(results) == 1
        assert results[0].hook_name == "failing"
        assert results[0].success is False

    @patch('lib.hooks.runner.subprocess.run')
    def test_run_hooks_non_blocking_continues_on_failure(self, mock_run):
        runner = HookRunner(agent_id="test-agent")
        runner._config = HooksConfig(hooks=[
            Hook(name="failing", trigger="pre-commit", command="exit 1", blocking=False),
            Hook(name="continues", trigger="pre-commit", command="echo ok")
        ])
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="error"),
            MagicMock(returncode=0, stdout="ok", stderr="")
        ]

        results = runner.run_hooks(HookTrigger.PRE_COMMIT)

        assert len(results) == 2


class TestRunSingleHook:
    """Tests for _run_hook method."""

    @pytest.fixture
    def runner(self):
        return HookRunner(agent_id="test-agent")

    @patch('lib.hooks.runner.subprocess.run')
    def test_run_hook_success(self, mock_run, runner):
        mock_run.return_value = MagicMock(returncode=0, stdout="output", stderr="")
        hook = Hook(name="test", trigger="pre-commit", command="echo test")

        result = runner._run_hook(hook, {})

        assert result.success is True
        assert result.exit_code == 0
        assert result.stdout == "output"

    @patch('lib.hooks.runner.subprocess.run')
    def test_run_hook_failure(self, mock_run, runner):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error msg")
        hook = Hook(name="test", trigger="pre-commit", command="exit 1")

        result = runner._run_hook(hook, {})

        assert result.success is False
        assert result.exit_code == 1
        assert result.stderr == "error msg"

    @patch('lib.hooks.runner.subprocess.run')
    def test_run_hook_timeout(self, mock_run, runner):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=5)
        hook = Hook(name="test", trigger="pre-commit", command="sleep 100", timeout=5)

        result = runner._run_hook(hook, {})

        assert result.success is False
        assert result.exit_code == -1
        assert "timed out" in result.stderr

    @patch('lib.hooks.runner.subprocess.run')
    def test_run_hook_exception(self, mock_run, runner):
        mock_run.side_effect = OSError("Command not found")
        hook = Hook(name="test", trigger="pre-commit", command="nonexistent")

        result = runner._run_hook(hook, {})

        assert result.success is False
        assert result.exit_code == -2
        assert "Command not found" in result.stderr

    @patch('lib.hooks.runner.subprocess.run')
    def test_run_hook_with_condition_true(self, mock_run, runner):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        hook = Hook(name="test", trigger="pre-commit", command="echo test", condition="x > 5")

        result = runner._run_hook(hook, {'x': 10})

        assert result.success is True
        assert result.skipped is False

    @patch('lib.hooks.runner.subprocess.run')
    def test_run_hook_with_condition_false(self, mock_run, runner):
        hook = Hook(name="test", trigger="pre-commit", command="echo test", condition="x > 5")

        result = runner._run_hook(hook, {'x': 3})

        assert result.success is True
        assert result.skipped is True
        assert result.skip_reason == "Condition not met"
        mock_run.assert_not_called()

    @patch('lib.hooks.runner.subprocess.run')
    def test_run_hook_sets_env_vars(self, mock_run, runner):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        hook = Hook(
            name="test-hook",
            trigger="pre-commit",
            command="echo test",
            env={"CUSTOM_VAR": "custom_value"}
        )

        runner._run_hook(hook, {})

        call_env = mock_run.call_args.kwargs['env']
        assert call_env['RALPH_AGENT_ID'] == "test-agent"
        assert call_env['RALPH_HOOK_NAME'] == "test-hook"
        assert call_env['RALPH_HOOK_TRIGGER'] == "pre-commit"
        assert call_env['CUSTOM_VAR'] == "custom_value"


class TestSubstituteVars:
    """Tests for _substitute_vars method."""

    @pytest.fixture
    def runner(self):
        return HookRunner()

    def test_substitute_simple_var(self, runner):
        result = runner._substitute_vars("echo ${NAME}", {'NAME': 'test'})
        assert result == "echo test"

    def test_substitute_multiple_vars(self, runner):
        result = runner._substitute_vars("${CMD} ${ARG1} ${ARG2}", {
            'CMD': 'npm',
            'ARG1': 'run',
            'ARG2': 'test'
        })
        assert result == "npm run test"

    def test_substitute_missing_var_safe(self, runner):
        result = runner._substitute_vars("echo ${MISSING}", {})
        assert result == "echo ${MISSING}"

    def test_substitute_with_special_chars(self, runner):
        result = runner._substitute_vars("grep '${PATTERN}' file.txt", {'PATTERN': 'test.*'})
        assert result == "grep 'test.*' file.txt"


class TestEvaluateCondition:
    """Tests for _evaluate_condition method."""

    @pytest.fixture
    def runner(self):
        return HookRunner()

    def test_evaluate_simple_comparison(self, runner):
        assert runner._evaluate_condition("x > 5", {'x': 10}) is True
        assert runner._evaluate_condition("x > 5", {'x': 3}) is False

    def test_evaluate_equality(self, runner):
        assert runner._evaluate_condition("status == 'active'", {'status': 'active'}) is True
        assert runner._evaluate_condition("status == 'active'", {'status': 'inactive'}) is False

    def test_evaluate_in_operator(self, runner):
        assert runner._evaluate_condition("'ts' in file", {'file': 'test.ts'}) is True
        assert runner._evaluate_condition("'py' in file", {'file': 'test.ts'}) is False

    def test_evaluate_invalid_returns_true(self, runner):
        result = runner._evaluate_condition("undefined_func()", {})
        assert result is True

    def test_evaluate_no_builtins_access(self, runner):
        result = runner._evaluate_condition("__import__('os').system('ls')", {})
        assert result is True


class TestLogResult:
    """Tests for _log_result method."""

    def test_log_result_without_redis(self):
        runner = HookRunner()
        result = HookResult(
            hook_name="test",
            success=True,
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=100
        )
        runner._log_result(result)

    def test_log_result_with_redis(self):
        mock_redis = MagicMock()
        runner = HookRunner(agent_id="agent-1", redis_client=mock_redis)
        result = HookResult(
            hook_name="test-hook",
            success=True,
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=100
        )

        runner._log_result(result)

        mock_redis.rpush.assert_called_once()
        call_args = mock_redis.rpush.call_args
        assert call_args[0][0] == "ralph:hooks:log:agent-1"

        logged_data = json.loads(call_args[0][1])
        assert logged_data['hook_name'] == "test-hook"
        assert logged_data['success'] is True
        assert logged_data['duration_ms'] == 100


class TestLifecycleHooks:
    """Tests for lifecycle hook methods."""

    @pytest.fixture
    def runner(self):
        runner = HookRunner(agent_id="test-agent")
        runner._config = HooksConfig(hooks=[])
        return runner

    @patch.object(HookRunner, 'run_hooks')
    def test_pre_commit_passes(self, mock_run_hooks, runner):
        mock_run_hooks.return_value = [
            HookResult("hook1", True, 0, "", "", 100),
            HookResult("hook2", True, 0, "", "", 100)
        ]

        result = runner.pre_commit(files=['file1.py', 'file2.py'])

        assert result is True
        mock_run_hooks.assert_called_once()
        call_args = mock_run_hooks.call_args
        assert call_args[0][0] == HookTrigger.PRE_COMMIT
        assert call_args[0][1]['FILES'] == ['file1.py', 'file2.py']

    @patch.object(HookRunner, 'run_hooks')
    def test_pre_commit_fails(self, mock_run_hooks, runner):
        mock_run_hooks.return_value = [
            HookResult("hook1", True, 0, "", "", 100),
            HookResult("hook2", False, 1, "", "error", 100)
        ]

        result = runner.pre_commit()

        assert result is False

    @patch.object(HookRunner, 'run_hooks')
    def test_pre_commit_skipped_counts_as_pass(self, mock_run_hooks, runner):
        mock_run_hooks.return_value = [
            HookResult("hook1", True, 0, "", "", 0, skipped=True)
        ]

        result = runner.pre_commit()

        assert result is True

    @patch.object(HookRunner, 'run_hooks')
    def test_post_commit(self, mock_run_hooks, runner):
        mock_run_hooks.return_value = []

        runner.post_commit("abc123")

        mock_run_hooks.assert_called_once()
        call_args = mock_run_hooks.call_args
        assert call_args[0][0] == HookTrigger.POST_COMMIT
        assert call_args[0][1]['COMMIT_SHA'] == "abc123"

    @patch.object(HookRunner, 'run_hooks')
    def test_pre_edit_allowed(self, mock_run_hooks, runner):
        mock_run_hooks.return_value = [
            HookResult("hook1", True, 0, "", "", 100)
        ]

        result = runner.pre_edit("/path/to/file.ts")

        assert result is True
        mock_run_hooks.assert_called_once_with(
            HookTrigger.PRE_EDIT, file_path="/path/to/file.ts"
        )

    @patch.object(HookRunner, 'run_hooks')
    def test_pre_edit_blocked(self, mock_run_hooks, runner):
        mock_run_hooks.return_value = [
            HookResult("lock-check", False, 1, "", "File is locked", 100)
        ]

        result = runner.pre_edit("/path/to/file.ts")

        assert result is False

    @patch.object(HookRunner, 'run_hooks')
    def test_post_edit(self, mock_run_hooks, runner):
        mock_run_hooks.return_value = []

        runner.post_edit("/path/to/file.ts")

        mock_run_hooks.assert_called_once_with(
            HookTrigger.POST_EDIT, file_path="/path/to/file.ts"
        )

    @patch.object(HookRunner, 'run_hooks')
    def test_pre_task_allowed(self, mock_run_hooks, runner):
        mock_run_hooks.return_value = [
            HookResult("hook1", True, 0, "", "", 100)
        ]

        result = runner.pre_task("task-123", "code_review")

        assert result is True
        call_args = mock_run_hooks.call_args
        assert call_args[0][1]['TASK_ID'] == "task-123"
        assert call_args[0][1]['TASK_TYPE'] == "code_review"

    @patch.object(HookRunner, 'run_hooks')
    def test_post_task_success(self, mock_run_hooks, runner):
        mock_run_hooks.return_value = []

        runner.post_task("task-123", "code_review", success=True)

        mock_run_hooks.assert_called_once()
        call_args = mock_run_hooks.call_args
        assert call_args[0][0] == HookTrigger.TASK_COMPLETE
        assert call_args[0][1]['TASK_SUCCESS'] is True

    @patch.object(HookRunner, 'run_hooks')
    def test_post_task_failure(self, mock_run_hooks, runner):
        mock_run_hooks.return_value = []

        runner.post_task("task-123", "code_review", success=False)

        mock_run_hooks.assert_called_once()
        call_args = mock_run_hooks.call_args
        assert call_args[0][0] == HookTrigger.TASK_FAIL
        assert call_args[0][1]['TASK_SUCCESS'] is False

    @patch.object(HookRunner, 'run_hooks')
    def test_on_error(self, mock_run_hooks, runner):
        mock_run_hooks.return_value = []

        runner.on_error("Something went wrong", context={'file': 'test.py'})

        mock_run_hooks.assert_called_once()
        call_args = mock_run_hooks.call_args
        assert call_args[0][0] == HookTrigger.ON_ERROR
        assert call_args[0][1]['ERROR'] == "Something went wrong"
        assert call_args[0][1]['file'] == 'test.py'


class TestHooksConfig:
    """Tests for HooksConfig class."""

    def test_load_from_json(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        try:
            json.dump({
                "version": "2.0",
                "globals": {"timeout_default": 30},
                "hooks": [
                    {"name": "hook1", "trigger": "pre-commit", "command": "echo 1"},
                    {"name": "hook2", "trigger": "post-commit", "command": "echo 2"}
                ]
            }, f)
            f.close()

            config = HooksConfig.load(f.name)

            assert config.version == "2.0"
            assert len(config.hooks) == 2
            assert config.globals['timeout_default'] == 30
        finally:
            try:
                os.unlink(f.name)
            except PermissionError:
                pass

    def test_get_hooks_for_trigger(self):
        config = HooksConfig(hooks=[
            Hook(name="h1", trigger="pre-commit", command="echo 1"),
            Hook(name="h2", trigger="pre-commit", command="echo 2"),
            Hook(name="h3", trigger="post-commit", command="echo 3"),
            Hook(name="h4", trigger="pre-commit", command="echo 4", enabled=False)
        ])

        pre_commit_hooks = config.get_hooks_for_trigger(HookTrigger.PRE_COMMIT)

        assert len(pre_commit_hooks) == 2
        assert all(h.trigger == "pre-commit" for h in pre_commit_hooks)

    def test_get_hooks_for_file(self):
        config = HooksConfig(hooks=[
            Hook(name="ts-only", trigger="pre-edit", command="echo ts", file_patterns=["*.ts"]),
            Hook(name="all-files", trigger="pre-edit", command="echo all"),
            Hook(name="py-only", trigger="pre-edit", command="echo py", file_patterns=["*.py"])
        ])

        ts_hooks = config.get_hooks_for_file("test.ts", HookTrigger.PRE_EDIT)

        assert len(ts_hooks) == 2
        hook_names = [h.name for h in ts_hooks]
        assert "ts-only" in hook_names
        assert "all-files" in hook_names
        assert "py-only" not in hook_names


class TestHook:
    """Tests for Hook dataclass."""

    def test_matches_file_no_patterns(self):
        hook = Hook(name="test", trigger="pre-edit", command="echo")
        assert hook.matches_file("any/file.txt") is True

    def test_matches_file_with_pattern(self):
        hook = Hook(name="test", trigger="pre-edit", command="echo", file_patterns=["*.ts", "*.tsx"])
        assert hook.matches_file("component.tsx") is True
        assert hook.matches_file("script.ts") is True
        assert hook.matches_file("script.py") is False

    def test_matches_file_with_exclude(self):
        hook = Hook(
            name="test",
            trigger="pre-edit",
            command="echo",
            file_patterns=["*.ts"],
            exclude_patterns=["*.test.ts", "*.spec.ts"]
        )
        assert hook.matches_file("component.ts") is True
        assert hook.matches_file("component.test.ts") is False
        assert hook.matches_file("component.spec.ts") is False

    def test_matches_file_glob_pattern(self):
        hook = Hook(
            name="test",
            trigger="pre-edit",
            command="echo",
            file_patterns=["src/**/*.ts"]
        )
        assert hook.matches_file("src/components/Button.ts") is True

    def test_default_values(self):
        hook = Hook(name="test", trigger="pre-commit", command="echo")
        assert hook.enabled is True
        assert hook.blocking is True
        assert hook.timeout == 60
        assert hook.on_failure == "abort"
        assert hook.condition is None


class TestHookTrigger:
    """Tests for HookTrigger enum."""

    def test_all_triggers_defined(self):
        expected = [
            "pre-commit", "post-commit",
            "pre-edit", "post-edit",
            "pre-task", "post-task",
            "task-complete", "task-fail",
            "on-error",
            "pre-build", "post-build",
            "pre-test", "post-test"
        ]
        actual = [t.value for t in HookTrigger]
        assert set(expected) == set(actual)

    def test_trigger_values(self):
        assert HookTrigger.PRE_COMMIT.value == "pre-commit"
        assert HookTrigger.POST_COMMIT.value == "post-commit"
        assert HookTrigger.ON_ERROR.value == "on-error"
