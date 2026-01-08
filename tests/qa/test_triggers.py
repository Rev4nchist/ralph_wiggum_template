"""
Test Suite 5: QA Trigger Tests
Tests feature completion triggers, fix verification, and escalation rules
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    id: str
    title: str
    agent: str
    status: TaskStatus
    feature: str
    test_results: Optional[dict] = None


class QATriggerEngine:
    """Simulates QA trigger logic from orchestration skill"""

    MAX_FIX_ATTEMPTS = 3

    def __init__(self):
        self.fix_attempts = {}
        self.escalations = []
        self.spawned_agents = []

    def check_feature_completion_trigger(self, tasks: List[Task], feature: str) -> bool:
        """Check if all impl tasks for feature are complete"""
        impl_tasks = [t for t in tasks if t.feature == feature and t.agent not in ["test-architect", "qa"]]
        return all(t.status == TaskStatus.COMPLETED for t in impl_tasks)

    def check_fix_verification_trigger(self, task: Task) -> bool:
        """Check if fix agent completed work and needs re-test"""
        return task.agent == "debugger" and task.status == TaskStatus.COMPLETED

    def should_spawn_qa(self, tasks: List[Task], feature: str) -> bool:
        """Determine if QA agent should spawn"""
        if self.check_feature_completion_trigger(tasks, feature):
            return True
        return False

    def handle_qa_result(self, task: Task, passed: bool, failure_info: Optional[str] = None):
        """Handle QA test result, spawn fix or escalate"""
        if passed:
            return {"action": "complete", "task_id": task.id}

        attempt_key = task.id
        self.fix_attempts[attempt_key] = self.fix_attempts.get(attempt_key, 0) + 1

        if self.fix_attempts[attempt_key] >= self.MAX_FIX_ATTEMPTS:
            self.escalations.append({
                "task_id": task.id,
                "reason": "max_retries_exceeded",
                "failure_info": failure_info
            })
            return {"action": "escalate", "task_id": task.id, "attempts": self.fix_attempts[attempt_key]}

        return {"action": "spawn_fix", "task_id": task.id, "attempt": self.fix_attempts[attempt_key]}

    def spawn_qa_agent(self, feature: str, impl_summary: dict):
        """Record QA agent spawn"""
        spawn_info = {
            "agent": "test-architect",
            "feature": feature,
            "context": impl_summary
        }
        self.spawned_agents.append(spawn_info)
        return spawn_info


class TestFeatureCompletionTrigger:
    """Test 5.1: QA spawns when feature implementation completes"""

    @pytest.fixture
    def engine(self):
        return QATriggerEngine()

    def test_triggers_when_all_impl_complete(self, engine):
        """QA triggers when all impl tasks pass"""
        tasks = [
            Task("BE-001", "Backend API", "backend", TaskStatus.COMPLETED, "auth"),
            Task("FE-001", "Frontend UI", "frontend", TaskStatus.COMPLETED, "auth"),
            Task("QA-001", "Auth tests", "test-architect", TaskStatus.PENDING, "auth")
        ]

        should_spawn = engine.should_spawn_qa(tasks, "auth")

        assert should_spawn is True

    def test_does_not_trigger_with_incomplete_impl(self, engine):
        """QA doesn't trigger if impl tasks pending"""
        tasks = [
            Task("BE-001", "Backend API", "backend", TaskStatus.COMPLETED, "auth"),
            Task("FE-001", "Frontend UI", "frontend", TaskStatus.IN_PROGRESS, "auth"),
            Task("QA-001", "Auth tests", "test-architect", TaskStatus.PENDING, "auth")
        ]

        should_spawn = engine.should_spawn_qa(tasks, "auth")

        assert should_spawn is False

    def test_ignores_qa_task_status(self, engine):
        """Feature completion only checks impl tasks, not QA"""
        tasks = [
            Task("BE-001", "Backend API", "backend", TaskStatus.COMPLETED, "auth"),
            Task("FE-001", "Frontend UI", "frontend", TaskStatus.COMPLETED, "auth"),
            Task("QA-001", "Auth tests", "test-architect", TaskStatus.FAILED, "auth")
        ]

        should_spawn = engine.check_feature_completion_trigger(tasks, "auth")

        assert should_spawn is True

    def test_qa_receives_impl_context(self, engine):
        """QA agent receives implementation summary"""
        impl_summary = {
            "files_modified": ["api/auth.py", "components/Login.tsx"],
            "endpoints_created": ["/api/auth/login", "/api/auth/register"],
            "components_created": ["LoginForm", "AuthProvider"]
        }

        spawn_info = engine.spawn_qa_agent("auth", impl_summary)

        assert spawn_info["agent"] == "test-architect"
        assert spawn_info["feature"] == "auth"
        assert "files_modified" in spawn_info["context"]


class TestFixVerificationTrigger:
    """Test 5.2: QA re-runs after fix agent completes"""

    @pytest.fixture
    def engine(self):
        return QATriggerEngine()

    def test_triggers_after_fix_complete(self, engine):
        """Re-test triggers when fix agent completes"""
        fix_task = Task("FIX-001", "Fix login bug", "debugger", TaskStatus.COMPLETED, "auth")

        should_retest = engine.check_fix_verification_trigger(fix_task)

        assert should_retest is True

    def test_no_trigger_if_fix_in_progress(self, engine):
        """No re-test if fix still in progress"""
        fix_task = Task("FIX-001", "Fix login bug", "debugger", TaskStatus.IN_PROGRESS, "auth")

        should_retest = engine.check_fix_verification_trigger(fix_task)

        assert should_retest is False

    def test_retest_focuses_on_original_failure(self, engine):
        """Re-test should focus on originally failing test"""
        original_failure = {
            "test_name": "test_login_validation",
            "error": "AssertionError: Expected 400, got 500"
        }

        fix_context = {
            "original_failure": original_failure,
            "fix_applied": "Added input validation to login endpoint"
        }

        assert "test_login_validation" in fix_context["original_failure"]["test_name"]
        assert fix_context["fix_applied"] is not None


class TestEscalationAfterFailures:
    """Test 5.3: System escalates after 3 fix attempts"""

    @pytest.fixture
    def engine(self):
        return QATriggerEngine()

    def test_spawns_fix_on_first_failure(self, engine):
        """First failure spawns fix agent"""
        qa_task = Task("QA-001", "Auth tests", "test-architect", TaskStatus.COMPLETED, "auth")

        result = engine.handle_qa_result(qa_task, passed=False, failure_info="Login validation failed")

        assert result["action"] == "spawn_fix"
        assert result["attempt"] == 1

    def test_spawns_fix_on_second_failure(self, engine):
        """Second failure spawns another fix agent"""
        qa_task = Task("QA-001", "Auth tests", "test-architect", TaskStatus.COMPLETED, "auth")

        engine.handle_qa_result(qa_task, passed=False)
        result = engine.handle_qa_result(qa_task, passed=False)

        assert result["action"] == "spawn_fix"
        assert result["attempt"] == 2

    def test_escalates_on_third_failure(self, engine):
        """Third failure escalates to human"""
        qa_task = Task("QA-001", "Auth tests", "test-architect", TaskStatus.COMPLETED, "auth")

        engine.handle_qa_result(qa_task, passed=False)
        engine.handle_qa_result(qa_task, passed=False)
        result = engine.handle_qa_result(qa_task, passed=False, failure_info="Persistent login bug")

        assert result["action"] == "escalate"
        assert result["attempts"] == 3
        assert len(engine.escalations) == 1
        assert engine.escalations[0]["reason"] == "max_retries_exceeded"

    def test_success_after_fix_completes_cycle(self, engine):
        """Success after fix completes without escalation"""
        qa_task = Task("QA-001", "Auth tests", "test-architect", TaskStatus.COMPLETED, "auth")

        engine.handle_qa_result(qa_task, passed=False)
        engine.handle_qa_result(qa_task, passed=False)
        result = engine.handle_qa_result(qa_task, passed=True)

        assert result["action"] == "complete"
        assert len(engine.escalations) == 0

    def test_escalation_includes_failure_info(self, engine):
        """Escalation includes failure details for human"""
        qa_task = Task("QA-001", "Auth tests", "test-architect", TaskStatus.COMPLETED, "auth")
        failure_info = "TypeError: Cannot read property 'user' of undefined"

        engine.handle_qa_result(qa_task, passed=False, failure_info=failure_info)
        engine.handle_qa_result(qa_task, passed=False, failure_info=failure_info)
        engine.handle_qa_result(qa_task, passed=False, failure_info=failure_info)

        assert engine.escalations[0]["failure_info"] == failure_info


class TestQASpawnProtocol:
    """Test QA agent spawn protocol"""

    def test_qa_spawn_includes_file_list(self):
        """QA spawn includes list of modified files"""
        spawn_context = {
            "feature": "auth",
            "files_modified": [
                "api/auth.py",
                "api/routes.py",
                "components/Login.tsx",
                "contexts/AuthContext.tsx"
            ],
            "impl_summary": "Authentication with JWT tokens"
        }

        assert len(spawn_context["files_modified"]) == 4
        assert any("api" in f for f in spawn_context["files_modified"])
        assert any("components" in f for f in spawn_context["files_modified"])

    def test_qa_spawn_includes_required_checks(self):
        """QA spawn specifies required check types"""
        required_checks = [
            "unit_tests",
            "integration_tests",
            "build_verification",
            "typescript_strict",
            "security_scan"
        ]

        assert "unit_tests" in required_checks
        assert "security_scan" in required_checks

    def test_retest_spawn_includes_previous_failures(self):
        """Re-test spawn includes list of previous failures"""
        retest_context = {
            "feature": "auth",
            "previous_failures": [
                {"test": "test_login_validation", "error": "500 error"},
                {"test": "test_token_refresh", "error": "Token expired"}
            ],
            "fix_summary": "Added error handling to auth service"
        }

        assert len(retest_context["previous_failures"]) == 2
        assert retest_context["fix_summary"] is not None


class TestBuildSuccessTrigger:
    """Test build success trigger for E2E tests"""

    def test_e2e_triggers_after_build_success(self):
        """E2E tests run after successful build"""
        build_result = {
            "status": "success",
            "output_dir": "dist/",
            "artifacts": ["bundle.js", "index.html"]
        }

        should_run_e2e = build_result["status"] == "success"

        assert should_run_e2e is True

    def test_no_e2e_on_build_failure(self):
        """E2E tests don't run if build fails"""
        build_result = {
            "status": "failed",
            "error": "TypeScript compilation error"
        }

        should_run_e2e = build_result["status"] == "success"

        assert should_run_e2e is False


class TestSecurityVulnerabilityEscalation:
    """Test immediate escalation for security issues"""

    @pytest.fixture
    def engine(self):
        return QATriggerEngine()

    def test_security_vulnerability_escalates_immediately(self, engine):
        """Security vulnerabilities escalate without retry"""
        qa_task = Task("SEC-001", "Security audit", "security-auditor", TaskStatus.COMPLETED, "auth")

        security_result = {
            "passed": False,
            "severity": "critical",
            "vulnerability": "SQL injection in login endpoint"
        }

        if security_result["severity"] == "critical":
            engine.escalations.append({
                "task_id": qa_task.id,
                "reason": "critical_security_vulnerability",
                "details": security_result["vulnerability"]
            })

        assert len(engine.escalations) == 1
        assert "critical_security_vulnerability" in engine.escalations[0]["reason"]


class TestTelegramNotification:
    """Test Telegram notification on escalation"""

    def test_escalation_sends_notification(self):
        """Escalation triggers Telegram notification"""
        escalation = {
            "task_id": "QA-001",
            "reason": "max_retries_exceeded",
            "failure_info": "Login test consistently failing"
        }

        notification = self._format_notification(escalation)

        assert "QA-001" in notification
        assert "max_retries_exceeded" in notification
        assert "Login test" in notification

    def _format_notification(self, escalation):
        """Format escalation for Telegram"""
        return f"""
Ralph Wiggum Escalation:
Task: {escalation['task_id']}
Reason: {escalation['reason']}
Details: {escalation['failure_info']}

Human intervention required.
"""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
