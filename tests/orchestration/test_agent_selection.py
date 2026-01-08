"""
Test Suite 2: Agent Type Selection Tests
Tests that generate-prd.sh assigns correct agent types based on task keywords
"""
import pytest
import json
import subprocess
import sys
import os
import tempfile
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "generate-prd.sh"
FIXTURES_PATH = PROJECT_ROOT / "tests" / "fixtures"


def jq_available():
    """Check if jq is available in WSL bash"""
    try:
        result = subprocess.run(
            ["bash", "-c", "which jq"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


JQ_AVAILABLE = jq_available()
requires_jq = pytest.mark.skipif(not JQ_AVAILABLE, reason="jq not available in WSL")


def to_posix_path(path):
    """Convert Windows path to POSIX style for WSL bash"""
    path_str = str(path)
    if os.name == 'nt':
        path_str = path_str.replace('\\', '/')
        if len(path_str) > 1 and path_str[1] == ':':
            path_str = '/mnt/' + path_str[0].lower() + path_str[2:]
    return path_str


@requires_jq
class TestAgentTypeMapping:
    """Test 2.1: Task-to-Agent Mapping"""

    @pytest.fixture
    def temp_project(self):
        """Create temporary project directory with taskmaster structure"""
        temp_dir = tempfile.mkdtemp()
        taskmaster_dir = Path(temp_dir) / ".taskmaster" / "tasks"
        taskmaster_dir.mkdir(parents=True)
        plans_dir = Path(temp_dir) / "plans"
        plans_dir.mkdir()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_backend_agent_selection(self, temp_project):
        """Tasks with backend keywords get backend agent"""
        tasks = {
            "tasks": [
                {"id": 1, "title": "Set up Docker environment", "status": "pending", "dependencies": []},
                {"id": 2, "title": "Create database migrations", "status": "pending", "dependencies": []},
                {"id": 3, "title": "Implement API endpoints", "status": "pending", "dependencies": []},
                {"id": 4, "title": "Configure FastAPI server", "status": "pending", "dependencies": []},
                {"id": 5, "title": "Build Python backend service", "status": "pending", "dependencies": []}
            ]
        }
        self._run_conversion(temp_project, tasks)
        prd = self._read_output(temp_project)

        for task in prd["tasks"]:
            assert task["agent"] == "backend", f"Task '{task['title']}' should have backend agent"
            assert task["type"] == "backend"

    def test_frontend_agent_selection(self, temp_project):
        """Tasks with frontend keywords get frontend agent"""
        tasks = {
            "tasks": [
                {"id": 1, "title": "Create React login form", "status": "pending", "dependencies": []},
                {"id": 2, "title": "Build UI components", "status": "pending", "dependencies": []},
                {"id": 3, "title": "Style with CSS modules", "status": "pending", "dependencies": []},
                {"id": 4, "title": "Implement frontend validation", "status": "pending", "dependencies": []},
                {"id": 5, "title": "Create Plasmo extension popup", "status": "pending", "dependencies": []}
            ]
        }
        self._run_conversion(temp_project, tasks)
        prd = self._read_output(temp_project)

        for task in prd["tasks"]:
            assert task["agent"] == "frontend", f"Task '{task['title']}' should have frontend agent"
            assert task["type"] == "frontend"

    def test_test_architect_agent_selection(self, temp_project):
        """Tasks with testing keywords get test-architect agent"""
        tasks = {
            "tasks": [
                {"id": 1, "title": "Write unit tests for auth", "status": "pending", "dependencies": []},
                {"id": 2, "title": "QA validation suite", "status": "pending", "dependencies": []},
                {"id": 3, "title": "Add test coverage reporting", "status": "pending", "dependencies": []},
                {"id": 4, "title": "Create validation tests", "status": "pending", "dependencies": []}
            ]
        }
        self._run_conversion(temp_project, tasks)
        prd = self._read_output(temp_project)

        for task in prd["tasks"]:
            assert task["agent"] == "test-architect", f"Task '{task['title']}' should have test-architect agent"
            assert task["type"] == "testing"

    def test_debugger_agent_selection(self, temp_project):
        """Tasks with debugging keywords get debugger agent"""
        tasks = {
            "tasks": [
                {"id": 1, "title": "Debug login error", "status": "pending", "dependencies": []},
                {"id": 2, "title": "Fix failing authentication", "status": "pending", "dependencies": []},
                {"id": 3, "title": "Resolve bug in user service", "status": "pending", "dependencies": []},
                {"id": 4, "title": "Fix error in checkout flow", "status": "pending", "dependencies": []}
            ]
        }
        self._run_conversion(temp_project, tasks)
        prd = self._read_output(temp_project)

        for task in prd["tasks"]:
            assert task["agent"] == "debugger", f"Task '{task['title']}' should have debugger agent"
            assert task["type"] == "debugging"

    def test_refactorer_agent_selection(self, temp_project):
        """Tasks with refactoring keywords get refactorer agent"""
        tasks = {
            "tasks": [
                {"id": 1, "title": "Refactor user service", "status": "pending", "dependencies": []},
                {"id": 2, "title": "Cleanup auth module", "status": "pending", "dependencies": []},
                {"id": 3, "title": "Address code smell in controller", "status": "pending", "dependencies": []},
                {"id": 4, "title": "Pay down technical debt", "status": "pending", "dependencies": []}
            ]
        }
        self._run_conversion(temp_project, tasks)
        prd = self._read_output(temp_project)

        for task in prd["tasks"]:
            assert task["agent"] == "refactorer", f"Task '{task['title']}' should have refactorer agent"
            assert task["type"] == "refactoring"

    def test_security_auditor_agent_selection(self, temp_project):
        """Tasks with security keywords get security-auditor agent"""
        tasks = {
            "tasks": [
                {"id": 1, "title": "Security audit for auth", "status": "pending", "dependencies": []},
                {"id": 2, "title": "Check for vulnerabilities", "status": "pending", "dependencies": []},
                {"id": 3, "title": "OWASP compliance review", "status": "pending", "dependencies": []},
                {"id": 4, "title": "Penetration testing setup", "status": "pending", "dependencies": []}
            ]
        }
        self._run_conversion(temp_project, tasks)
        prd = self._read_output(temp_project)

        for task in prd["tasks"]:
            assert task["agent"] == "security-auditor", f"Task '{task['title']}' should have security-auditor agent"
            assert task["type"] == "security"

    def test_docs_writer_agent_selection(self, temp_project):
        """Tasks with documentation keywords get docs-writer agent"""
        tasks = {
            "tasks": [
                {"id": 1, "title": "Update API documentation", "status": "pending", "dependencies": []},
                {"id": 2, "title": "Write README for module", "status": "pending", "dependencies": []},
                {"id": 3, "title": "Create user guide", "status": "pending", "dependencies": []},
                {"id": 4, "title": "Document API endpoints", "status": "pending", "dependencies": []}
            ]
        }
        self._run_conversion(temp_project, tasks)
        prd = self._read_output(temp_project)

        for task in prd["tasks"]:
            assert task["agent"] == "docs-writer", f"Task '{task['title']}' should have docs-writer agent"
            assert task["type"] == "docs"

    def test_code_reviewer_agent_selection(self, temp_project):
        """Tasks with review keywords get code-reviewer agent"""
        tasks = {
            "tasks": [
                {"id": 1, "title": "Review pull request #123", "status": "pending", "dependencies": []},
                {"id": 2, "title": "Code review for auth feature", "status": "pending", "dependencies": []},
                {"id": 3, "title": "PR review for login form", "status": "pending", "dependencies": []}
            ]
        }
        self._run_conversion(temp_project, tasks)
        prd = self._read_output(temp_project)

        for task in prd["tasks"]:
            assert task["agent"] == "code-reviewer", f"Task '{task['title']}' should have code-reviewer agent"
            assert task["type"] == "review"

    def test_general_purpose_fallback(self, temp_project):
        """Tasks without specific keywords get general-purpose agent"""
        tasks = {
            "tasks": [
                {"id": 1, "title": "Set up project structure", "status": "pending", "dependencies": []},
                {"id": 2, "title": "Plan architecture approach", "status": "pending", "dependencies": []},
                {"id": 3, "title": "Research best practices", "status": "pending", "dependencies": []}
            ]
        }
        self._run_conversion(temp_project, tasks)
        prd = self._read_output(temp_project)

        for task in prd["tasks"]:
            assert task["agent"] == "general-purpose", f"Task '{task['title']}' should have general-purpose agent"

    def _run_conversion(self, project_dir, tasks):
        """Write tasks.json and run generate-prd.sh"""
        tasks_file = Path(project_dir) / ".taskmaster" / "tasks" / "tasks.json"
        with open(tasks_file, "w") as f:
            json.dump(tasks, f)

        script_path = to_posix_path(SCRIPT_PATH)
        proj_path = to_posix_path(project_dir)

        result = subprocess.run(
            ["bash", script_path, proj_path, "--from-taskmaster"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT)
        )
        if result.returncode != 0:
            pytest.fail(f"generate-prd.sh failed: {result.stderr}")

    def _read_output(self, project_dir):
        """Read generated prd.json"""
        prd_file = Path(project_dir) / "plans" / "prd.json"
        with open(prd_file) as f:
            return json.load(f)


@requires_jq
class TestAllSevenAgentTypes:
    """Test 2.2: All 7 Agent Types Recognized"""

    EXPECTED_AGENTS = [
        "general-purpose",
        "code-reviewer",
        "debugger",
        "test-architect",
        "refactorer",
        "security-auditor",
        "docs-writer",
        "backend",
        "frontend"
    ]

    @pytest.fixture
    def temp_project(self):
        """Create temporary project directory"""
        temp_dir = tempfile.mkdtemp()
        taskmaster_dir = Path(temp_dir) / ".taskmaster" / "tasks"
        taskmaster_dir.mkdir(parents=True)
        plans_dir = Path(temp_dir) / "plans"
        plans_dir.mkdir()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_all_agent_types_in_single_prd(self, temp_project):
        """PRD with diverse tasks assigns all agent types correctly"""
        tasks = {
            "tasks": [
                {"id": 1, "title": "Set up Docker backend", "status": "pending", "dependencies": []},
                {"id": 2, "title": "Create React form component", "status": "pending", "dependencies": []},
                {"id": 3, "title": "Write unit tests for auth", "status": "pending", "dependencies": []},
                {"id": 4, "title": "Debug login error handling", "status": "pending", "dependencies": []},
                {"id": 5, "title": "Refactor user service cleanup", "status": "pending", "dependencies": []},
                {"id": 6, "title": "Security audit for auth", "status": "pending", "dependencies": []},
                {"id": 7, "title": "Update API documentation", "status": "pending", "dependencies": []},
                {"id": 8, "title": "Review pull request", "status": "pending", "dependencies": []},
                {"id": 9, "title": "Plan architecture design", "status": "pending", "dependencies": []}
            ]
        }

        tasks_file = Path(temp_project) / ".taskmaster" / "tasks" / "tasks.json"
        with open(tasks_file, "w") as f:
            json.dump(tasks, f)

        script_path = to_posix_path(SCRIPT_PATH)
        proj_path = to_posix_path(temp_project)

        result = subprocess.run(
            ["bash", script_path, proj_path, "--from-taskmaster"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT)
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"

        prd_file = Path(temp_project) / "plans" / "prd.json"
        with open(prd_file) as f:
            prd = json.load(f)

        assigned_agents = {task["agent"] for task in prd["tasks"]}

        expected_in_test = {
            "backend", "frontend", "test-architect", "debugger",
            "refactorer", "security-auditor", "docs-writer",
            "code-reviewer", "general-purpose"
        }
        assert assigned_agents == expected_in_test, f"Missing agents: {expected_in_test - assigned_agents}"

    def test_agent_type_priority_order(self, temp_project):
        """Specialist agents take priority over domain agents"""
        tasks = {
            "tasks": [
                {"id": 1, "title": "Debug API endpoint error", "status": "pending", "dependencies": []},
            ]
        }

        tasks_file = Path(temp_project) / ".taskmaster" / "tasks" / "tasks.json"
        with open(tasks_file, "w") as f:
            json.dump(tasks, f)

        script_path = to_posix_path(SCRIPT_PATH)
        proj_path = to_posix_path(temp_project)

        result = subprocess.run(
            ["bash", script_path, proj_path, "--from-taskmaster"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT)
        )

        prd_file = Path(temp_project) / "plans" / "prd.json"
        with open(prd_file) as f:
            prd = json.load(f)

        assert prd["tasks"][0]["agent"] == "debugger"


@requires_jq
class TestTaskIdNormalization:
    """Test task ID formatting"""

    @pytest.fixture
    def temp_project(self):
        temp_dir = tempfile.mkdtemp()
        taskmaster_dir = Path(temp_dir) / ".taskmaster" / "tasks"
        taskmaster_dir.mkdir(parents=True)
        plans_dir = Path(temp_dir) / "plans"
        plans_dir.mkdir()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_numeric_ids_normalized(self, temp_project):
        """Numeric task IDs are normalized to TASK-XXX format"""
        tasks = {
            "tasks": [
                {"id": 1, "title": "First task", "status": "pending", "dependencies": []},
                {"id": 2, "title": "Second task", "status": "pending", "dependencies": [1]},
                {"id": 10, "title": "Tenth task", "status": "pending", "dependencies": []}
            ]
        }

        tasks_file = Path(temp_project) / ".taskmaster" / "tasks" / "tasks.json"
        with open(tasks_file, "w") as f:
            json.dump(tasks, f)

        script_path = to_posix_path(SCRIPT_PATH)
        proj_path = to_posix_path(temp_project)

        subprocess.run(
            ["bash", script_path, proj_path, "--from-taskmaster"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT)
        )

        prd_file = Path(temp_project) / "plans" / "prd.json"
        with open(prd_file) as f:
            prd = json.load(f)

        ids = [task["id"] for task in prd["tasks"]]
        assert "TASK-001" in ids
        assert "TASK-002" in ids
        assert "TASK-010" in ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
