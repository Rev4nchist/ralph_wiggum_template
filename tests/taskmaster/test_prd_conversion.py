"""
Test Suite 3: Taskmaster Pipeline Tests
Tests PRD parsing, Ralph format conversion, and dependency preservation
"""
import pytest
import json
import subprocess
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
class TestRalphFormatConversion:
    """Test 3.2: generate-prd.sh converts to correct format"""

    @pytest.fixture
    def temp_project(self):
        temp_dir = tempfile.mkdtemp()
        taskmaster_dir = Path(temp_dir) / ".taskmaster" / "tasks"
        taskmaster_dir.mkdir(parents=True)
        plans_dir = Path(temp_dir) / "plans"
        plans_dir.mkdir()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_output_has_required_structure(self, temp_project):
        """Output prd.json has project, created_at, tasks"""
        tasks = self._sample_tasks()
        self._write_tasks(temp_project, tasks)
        self._run_conversion(temp_project)

        prd = self._read_output(temp_project)

        assert "project" in prd, "Missing 'project' field"
        assert "created_at" in prd, "Missing 'created_at' field"
        assert "tasks" in prd, "Missing 'tasks' field"
        assert isinstance(prd["tasks"], list), "'tasks' should be a list"

    def test_each_task_has_required_fields(self, temp_project):
        """Each task has id, title, description, type, agent, deps, acceptance_criteria, passes"""
        tasks = self._sample_tasks()
        self._write_tasks(temp_project, tasks)
        self._run_conversion(temp_project)

        prd = self._read_output(temp_project)

        required_fields = ["id", "title", "description", "type", "agent", "deps", "acceptance_criteria", "passes"]
        for task in prd["tasks"]:
            for field in required_fields:
                assert field in task, f"Task missing required field: {field}"

    def test_task_ids_normalized_format(self, temp_project):
        """Task IDs are normalized to TASK-XXX format"""
        tasks = {"tasks": [
            {"id": 1, "title": "Task one", "status": "pending", "dependencies": []},
            {"id": 5, "title": "Task five", "status": "pending", "dependencies": []},
            {"id": 12, "title": "Task twelve", "status": "pending", "dependencies": []}
        ]}
        self._write_tasks(temp_project, tasks)
        self._run_conversion(temp_project)

        prd = self._read_output(temp_project)

        ids = [t["id"] for t in prd["tasks"]]
        assert all(id.startswith("TASK-") for id in ids), "IDs should start with TASK-"
        assert all(len(id) == 8 for id in ids), "IDs should be TASK-XXX format"

    def test_agent_types_assigned_based_on_content(self, temp_project):
        """Agent types assigned based on task content/title"""
        tasks = {"tasks": [
            {"id": 1, "title": "Create API endpoint", "status": "pending", "dependencies": []},
            {"id": 2, "title": "Build React component", "status": "pending", "dependencies": []},
            {"id": 3, "title": "Write tests for auth", "status": "pending", "dependencies": []}
        ]}
        self._write_tasks(temp_project, tasks)
        self._run_conversion(temp_project)

        prd = self._read_output(temp_project)

        agents = {t["title"]: t["agent"] for t in prd["tasks"]}
        assert agents["Create API endpoint"] == "backend"
        assert agents["Build React component"] == "frontend"
        assert agents["Write tests for auth"] == "test-architect"

    def test_acceptance_criteria_from_subtasks(self, temp_project):
        """Acceptance criteria populated from subtasks"""
        tasks = {"tasks": [
            {
                "id": 1,
                "title": "Implement login",
                "status": "pending",
                "dependencies": [],
                "subtasks": [
                    {"title": "Create login form"},
                    {"title": "Add validation"},
                    {"title": "Handle errors"}
                ]
            }
        ]}
        self._write_tasks(temp_project, tasks)
        self._run_conversion(temp_project)

        prd = self._read_output(temp_project)

        criteria = prd["tasks"][0]["acceptance_criteria"]
        assert len(criteria) == 3
        assert "Create login form" in criteria
        assert "Add validation" in criteria
        assert "Handle errors" in criteria

    def test_passes_false_for_pending(self, temp_project):
        """Pending tasks have passes=false"""
        tasks = {"tasks": [
            {"id": 1, "title": "Pending task", "status": "pending", "dependencies": []}
        ]}
        self._write_tasks(temp_project, tasks)
        self._run_conversion(temp_project)

        prd = self._read_output(temp_project)

        assert prd["tasks"][0]["passes"] is False

    def test_passes_true_for_done(self, temp_project):
        """Done tasks have passes=true"""
        tasks = {"tasks": [
            {"id": 1, "title": "Done task", "status": "done", "dependencies": []}
        ]}
        self._write_tasks(temp_project, tasks)
        self._run_conversion(temp_project)

        prd = self._read_output(temp_project)

        assert prd["tasks"][0]["passes"] is True

    def _sample_tasks(self):
        return {"tasks": [
            {"id": 1, "title": "Set up project", "status": "pending", "dependencies": [], "subtasks": [{"title": "Init repo"}]},
            {"id": 2, "title": "Build feature", "status": "pending", "dependencies": [1], "subtasks": [{"title": "Add code"}]},
            {"id": 3, "title": "Write tests", "status": "pending", "dependencies": [2], "subtasks": [{"title": "Unit tests"}]}
        ]}

    def _write_tasks(self, project_dir, tasks):
        tasks_file = Path(project_dir) / ".taskmaster" / "tasks" / "tasks.json"
        with open(tasks_file, "w") as f:
            json.dump(tasks, f)

    def _run_conversion(self, project_dir):
        script_path = to_posix_path(SCRIPT_PATH)
        proj_path = to_posix_path(project_dir)
        result = subprocess.run(
            ["bash", script_path, proj_path, "--from-taskmaster"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT)
        )
        if result.returncode != 0:
            pytest.fail(f"Conversion failed: {result.stderr}")

    def _read_output(self, project_dir):
        prd_file = Path(project_dir) / "plans" / "prd.json"
        with open(prd_file) as f:
            return json.load(f)


@requires_jq
class TestDependencyPreservation:
    """Test 3.3: Dependencies survive format conversion"""

    @pytest.fixture
    def temp_project(self):
        temp_dir = tempfile.mkdtemp()
        taskmaster_dir = Path(temp_dir) / ".taskmaster" / "tasks"
        taskmaster_dir.mkdir(parents=True)
        plans_dir = Path(temp_dir) / "plans"
        plans_dir.mkdir()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_simple_dependencies_preserved(self, temp_project):
        """Simple A→B dependency is preserved"""
        tasks = {"tasks": [
            {"id": 1, "title": "Task A", "status": "pending", "dependencies": []},
            {"id": 2, "title": "Task B", "status": "pending", "dependencies": [1]}
        ]}
        self._write_and_convert(temp_project, tasks)
        prd = self._read_output(temp_project)

        task_b = next(t for t in prd["tasks"] if t["title"] == "Task B")
        assert task_b["deps"] == [1]

    def test_multiple_dependencies_preserved(self, temp_project):
        """Task with multiple dependencies [A, B]→C preserved"""
        tasks = {"tasks": [
            {"id": 1, "title": "Task A", "status": "pending", "dependencies": []},
            {"id": 2, "title": "Task B", "status": "pending", "dependencies": []},
            {"id": 3, "title": "Task C", "status": "pending", "dependencies": [1, 2]}
        ]}
        self._write_and_convert(temp_project, tasks)
        prd = self._read_output(temp_project)

        task_c = next(t for t in prd["tasks"] if t["title"] == "Task C")
        assert set(task_c["deps"]) == {1, 2}

    def test_chain_dependencies_preserved(self, temp_project):
        """Chain A→B→C→D preserved"""
        tasks = {"tasks": [
            {"id": 1, "title": "Task A", "status": "pending", "dependencies": []},
            {"id": 2, "title": "Task B", "status": "pending", "dependencies": [1]},
            {"id": 3, "title": "Task C", "status": "pending", "dependencies": [2]},
            {"id": 4, "title": "Task D", "status": "pending", "dependencies": [3]}
        ]}
        self._write_and_convert(temp_project, tasks)
        prd = self._read_output(temp_project)

        deps_map = {t["title"]: t["deps"] for t in prd["tasks"]}
        assert deps_map["Task A"] == []
        assert deps_map["Task B"] == [1]
        assert deps_map["Task C"] == [2]
        assert deps_map["Task D"] == [3]

    def test_diamond_dependencies_preserved(self, temp_project):
        """Diamond pattern A→[B,C]→D preserved"""
        tasks = {"tasks": [
            {"id": 1, "title": "Task A", "status": "pending", "dependencies": []},
            {"id": 2, "title": "Task B", "status": "pending", "dependencies": [1]},
            {"id": 3, "title": "Task C", "status": "pending", "dependencies": [1]},
            {"id": 4, "title": "Task D", "status": "pending", "dependencies": [2, 3]}
        ]}
        self._write_and_convert(temp_project, tasks)
        prd = self._read_output(temp_project)

        task_d = next(t for t in prd["tasks"] if t["title"] == "Task D")
        assert set(task_d["deps"]) == {2, 3}

    def test_no_circular_dependencies_introduced(self, temp_project):
        """Conversion doesn't introduce circular dependencies"""
        tasks = {"tasks": [
            {"id": 1, "title": "Task A", "status": "pending", "dependencies": []},
            {"id": 2, "title": "Task B", "status": "pending", "dependencies": [1]},
            {"id": 3, "title": "Task C", "status": "pending", "dependencies": [2]}
        ]}
        self._write_and_convert(temp_project, tasks)
        prd = self._read_output(temp_project)

        deps = {t["id"]: t["deps"] for t in prd["tasks"]}

        def has_cycle(task_id, visited=None):
            if visited is None:
                visited = set()
            if task_id in visited:
                return True
            visited.add(task_id)
            for dep in deps.get(task_id, []):
                dep_id = f"TASK-{str(dep).zfill(3)}"
                if dep_id in deps and has_cycle(dep_id, visited.copy()):
                    return True
            return False

        for task in prd["tasks"]:
            assert not has_cycle(task["id"]), f"Circular dependency detected for {task['id']}"

    def _write_and_convert(self, project_dir, tasks):
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
        assert result.returncode == 0, f"Conversion failed: {result.stderr}"

    def _read_output(self, project_dir):
        prd_file = Path(project_dir) / "plans" / "prd.json"
        with open(prd_file) as f:
            return json.load(f)


@requires_jq
class TestPriorityMapping:
    """Test priority string to number conversion"""

    @pytest.fixture
    def temp_project(self):
        temp_dir = tempfile.mkdtemp()
        taskmaster_dir = Path(temp_dir) / ".taskmaster" / "tasks"
        taskmaster_dir.mkdir(parents=True)
        plans_dir = Path(temp_dir) / "plans"
        plans_dir.mkdir()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_high_priority_mapping(self, temp_project):
        """High priority maps to 9"""
        tasks = {"tasks": [
            {"id": 1, "title": "High priority task", "status": "pending", "dependencies": [], "priority": "high"}
        ]}
        self._write_and_convert(temp_project, tasks)
        prd = self._read_output(temp_project)

        assert prd["tasks"][0]["priority"] == 9

    def test_medium_priority_mapping(self, temp_project):
        """Medium priority maps to 5"""
        tasks = {"tasks": [
            {"id": 1, "title": "Medium priority task", "status": "pending", "dependencies": [], "priority": "medium"}
        ]}
        self._write_and_convert(temp_project, tasks)
        prd = self._read_output(temp_project)

        assert prd["tasks"][0]["priority"] == 5

    def test_low_priority_mapping(self, temp_project):
        """Low priority maps to 3"""
        tasks = {"tasks": [
            {"id": 1, "title": "Low priority task", "status": "pending", "dependencies": [], "priority": "low"}
        ]}
        self._write_and_convert(temp_project, tasks)
        prd = self._read_output(temp_project)

        assert prd["tasks"][0]["priority"] == 3

    def test_numeric_priority_preserved(self, temp_project):
        """Numeric priority passes through unchanged"""
        tasks = {"tasks": [
            {"id": 1, "title": "Numeric priority task", "status": "pending", "dependencies": [], "priority": 7}
        ]}
        self._write_and_convert(temp_project, tasks)
        prd = self._read_output(temp_project)

        assert prd["tasks"][0]["priority"] == 7

    def _write_and_convert(self, project_dir, tasks):
        tasks_file = Path(project_dir) / ".taskmaster" / "tasks" / "tasks.json"
        with open(tasks_file, "w") as f:
            json.dump(tasks, f)

        script_path = to_posix_path(SCRIPT_PATH)
        proj_path = to_posix_path(project_dir)
        subprocess.run(
            ["bash", script_path, proj_path, "--from-taskmaster"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT)
        )

    def _read_output(self, project_dir):
        prd_file = Path(project_dir) / "plans" / "prd.json"
        with open(prd_file) as f:
            return json.load(f)


@requires_jq
class TestErrorHandling:
    """Test error handling for invalid inputs"""

    @pytest.fixture
    def temp_project(self):
        temp_dir = tempfile.mkdtemp()
        taskmaster_dir = Path(temp_dir) / ".taskmaster" / "tasks"
        taskmaster_dir.mkdir(parents=True)
        plans_dir = Path(temp_dir) / "plans"
        plans_dir.mkdir()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_missing_tasks_file_error(self, temp_project):
        """Error when tasks.json doesn't exist"""
        script_path = to_posix_path(SCRIPT_PATH)
        proj_path = to_posix_path(temp_project)
        result = subprocess.run(
            ["bash", script_path, proj_path, "--from-taskmaster"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT)
        )
        assert result.returncode != 0

    def test_empty_tasks_array(self, temp_project):
        """Handle empty tasks array gracefully"""
        tasks = {"tasks": []}
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

        assert result.returncode == 0

        prd_file = Path(temp_project) / "plans" / "prd.json"
        with open(prd_file) as f:
            prd = json.load(f)

        assert prd["tasks"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
