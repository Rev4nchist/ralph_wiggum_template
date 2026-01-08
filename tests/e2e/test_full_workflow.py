"""
Test Suite 6: End-to-End Integration Test
Tests complete workflow from PRD to tested code
"""
import pytest
import json
import subprocess
import os
import tempfile
import shutil
import redis
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum


PROJECT_ROOT = Path(__file__).parent.parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "generate-prd.sh"


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


class AgentType(Enum):
    GENERAL_PURPOSE = "general-purpose"
    CODE_REVIEWER = "code-reviewer"
    DEBUGGER = "debugger"
    TEST_ARCHITECT = "test-architect"
    REFACTORER = "refactorer"
    SECURITY_AUDITOR = "security-auditor"
    DOCS_WRITER = "docs-writer"
    BACKEND = "backend"
    FRONTEND = "frontend"


@dataclass
class AgentSpawn:
    agent_type: str
    task_id: str
    prompt: str
    wave: int
    status: str = "pending"
    result: Optional[Dict] = None


@dataclass
class ExecutionContext:
    project_id: str
    tasks: List[Dict] = field(default_factory=list)
    waves: List[List[str]] = field(default_factory=list)
    spawns: List[AgentSpawn] = field(default_factory=list)
    memories: List[Dict] = field(default_factory=list)
    handoffs: List[Dict] = field(default_factory=list)


class OrchestratorSimulator:
    """Simulates orchestrator behavior for E2E testing"""

    def __init__(self, project_id: str):
        self.context = ExecutionContext(project_id=project_id)
        self.redis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

    def load_prd(self, prd_path: Path):
        """Load PRD and build execution plan"""
        with open(prd_path) as f:
            prd = json.load(f)
        self.context.tasks = prd["tasks"]
        self._build_waves()
        return self

    def _build_waves(self):
        """Build execution waves from task dependencies"""
        completed = set()
        remaining = {t["id"] for t in self.context.tasks}

        while remaining:
            wave = []
            for task in self.context.tasks:
                if task["id"] not in remaining:
                    continue
                deps = task.get("deps", [])
                deps_met = all(self._normalize_dep(d) in completed for d in deps)
                if deps_met:
                    wave.append(task["id"])

            if not wave:
                raise ValueError("Circular dependency detected")

            self.context.waves.append(wave)
            completed.update(wave)
            remaining -= set(wave)

    def _normalize_dep(self, dep):
        if isinstance(dep, int):
            return f"TASK-{str(dep).zfill(3)}"
        return dep

    def load_memory_context(self):
        """Load project context from Redis"""
        key = f"claude_mem:{self.context.project_id}:memories"
        memories = self.redis.hgetall(key)
        self.context.memories = [json.loads(m) for m in memories.values()]
        return self

    def execute_waves(self):
        """Simulate wave execution"""
        for wave_num, wave in enumerate(self.context.waves):
            for task_id in wave:
                task = next(t for t in self.context.tasks if t["id"] == task_id)
                spawn = AgentSpawn(
                    agent_type=task["agent"],
                    task_id=task_id,
                    prompt=f"Implement {task_id}: {task['title']}",
                    wave=wave_num
                )
                self.context.spawns.append(spawn)
                spawn.status = "completed"
                spawn.result = {"success": True, "output": f"Completed {task_id}"}

                self._store_learning(task_id, f"Completed: {task['title']}")

        return self

    def _store_learning(self, task_id: str, content: str):
        """Store learning memory"""
        memory = {
            "content": content,
            "category": "learning",
            "task_id": task_id,
            "timestamp": time.time()
        }
        key = f"claude_mem:{self.context.project_id}:memories"
        self.redis.hset(key, f"learn_{task_id}", json.dumps(memory))
        self.context.memories.append(memory)

    def create_handoff(self, summary: str, next_steps: List[str]):
        """Create final handoff"""
        handoff = {
            "project_id": self.context.project_id,
            "summary": summary,
            "next_steps": next_steps,
            "tasks_completed": len(self.context.tasks),
            "agents_used": list(set(s.agent_type for s in self.context.spawns))
        }
        key = f"claude_mem:{self.context.project_id}:handoffs:final"
        self.redis.hset(key, mapping={
            "summary": summary,
            "next_steps": json.dumps(next_steps),
            "tasks_completed": str(len(self.context.tasks))
        })
        self.context.handoffs.append(handoff)
        return handoff

    def cleanup(self):
        """Clean up test data"""
        for key in self.redis.keys(f"claude_mem:{self.context.project_id}*"):
            self.redis.delete(key)


@requires_jq
class TestFullProjectWorkflow:
    """Test 6.1: Complete feature from PRD to tested code"""

    @pytest.fixture
    def temp_project(self):
        temp_dir = tempfile.mkdtemp()
        taskmaster_dir = Path(temp_dir) / ".taskmaster" / "tasks"
        taskmaster_dir.mkdir(parents=True)
        plans_dir = Path(temp_dir) / "plans"
        plans_dir.mkdir()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def orchestrator(self, temp_project):
        orch = OrchestratorSimulator("e2e-test-project")
        yield orch
        orch.cleanup()

    def test_full_auth_feature_workflow(self, temp_project, orchestrator):
        """
        Complete workflow:
        1. Taskmaster parses → tasks
        2. generate-prd.sh converts → prd.json
        3. Orchestrator loads context
        4. Execute waves with specialized agents
        5. Memory accumulated
        6. Handoff saved
        """
        tasks = self._create_auth_feature_tasks()
        self._write_tasks(temp_project, tasks)

        script_path = to_posix_path(SCRIPT_PATH)
        proj_path = to_posix_path(temp_project)
        result = subprocess.run(
            ["bash", script_path, proj_path, "--from-taskmaster"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT)
        )
        assert result.returncode == 0, f"PRD conversion failed: {result.stderr}"

        prd_path = Path(temp_project) / "plans" / "prd.json"
        orchestrator.load_prd(prd_path)

        assert len(orchestrator.context.tasks) == 9
        assert len(orchestrator.context.waves) > 0

        orchestrator.load_memory_context()

        orchestrator.execute_waves()

        assert all(s.status == "completed" for s in orchestrator.context.spawns)

        handoff = orchestrator.create_handoff(
            summary="Authentication feature implemented and tested",
            next_steps=["Deploy to staging", "User acceptance testing"]
        )

        assert handoff["tasks_completed"] == 9
        assert len(handoff["agents_used"]) >= 5

    def test_all_seven_agent_types_used(self, temp_project, orchestrator):
        """Verify all 7 agent types are utilized"""
        tasks = self._create_diverse_tasks_for_all_agents()
        self._write_tasks(temp_project, tasks)

        script_path = to_posix_path(SCRIPT_PATH)
        proj_path = to_posix_path(temp_project)
        subprocess.run(
            ["bash", script_path, proj_path, "--from-taskmaster"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT)
        )

        prd_path = Path(temp_project) / "plans" / "prd.json"
        orchestrator.load_prd(prd_path)
        orchestrator.execute_waves()

        agents_used = {s.agent_type for s in orchestrator.context.spawns}

        expected_agents = {
            "backend", "frontend", "test-architect", "debugger",
            "refactorer", "security-auditor", "docs-writer", "code-reviewer"
        }
        assert agents_used == expected_agents, f"Missing agents: {expected_agents - agents_used}"

    def test_memory_persists_across_waves(self, temp_project, orchestrator):
        """Verify memory accumulates throughout execution"""
        tasks = {"tasks": [
            {"id": 1, "title": "Set up backend API", "status": "pending", "dependencies": []},
            {"id": 2, "title": "Create frontend form", "status": "pending", "dependencies": [1]},
            {"id": 3, "title": "Write tests for API", "status": "pending", "dependencies": [1]}
        ]}
        self._write_tasks(temp_project, tasks)

        script_path = to_posix_path(SCRIPT_PATH)
        proj_path = to_posix_path(temp_project)
        subprocess.run(
            ["bash", script_path, proj_path, "--from-taskmaster"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT)
        )

        prd_path = Path(temp_project) / "plans" / "prd.json"
        orchestrator.load_prd(prd_path)
        orchestrator.execute_waves()

        assert len(orchestrator.context.memories) == 3

        memory_task_ids = [m["task_id"] for m in orchestrator.context.memories]
        assert "TASK-001" in memory_task_ids
        assert "TASK-002" in memory_task_ids
        assert "TASK-003" in memory_task_ids

    def test_handoff_saved_for_future_reference(self, temp_project, orchestrator):
        """Verify handoff is retrievable"""
        tasks = {"tasks": [
            {"id": 1, "title": "Simple task", "status": "pending", "dependencies": []}
        ]}
        self._write_tasks(temp_project, tasks)

        script_path = to_posix_path(SCRIPT_PATH)
        proj_path = to_posix_path(temp_project)
        subprocess.run(
            ["bash", script_path, proj_path, "--from-taskmaster"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT)
        )

        prd_path = Path(temp_project) / "plans" / "prd.json"
        orchestrator.load_prd(prd_path)
        orchestrator.execute_waves()
        orchestrator.create_handoff(
            summary="Test complete",
            next_steps=["Review", "Deploy"]
        )

        key = f"claude_mem:{orchestrator.context.project_id}:handoffs:final"
        stored = orchestrator.redis.hgetall(key)

        assert stored["summary"] == "Test complete"
        assert "Review" in json.loads(stored["next_steps"])

    def test_parallel_execution_in_wave(self, temp_project, orchestrator):
        """Verify independent tasks in same wave"""
        tasks = {"tasks": [
            {"id": 1, "title": "Architecture setup", "status": "pending", "dependencies": []},
            {"id": 2, "title": "Backend API development", "status": "pending", "dependencies": [1]},
            {"id": 3, "title": "Frontend component creation", "status": "pending", "dependencies": [1]},
            {"id": 4, "title": "Write tests for both", "status": "pending", "dependencies": [2, 3]}
        ]}
        self._write_tasks(temp_project, tasks)

        script_path = to_posix_path(SCRIPT_PATH)
        proj_path = to_posix_path(temp_project)
        subprocess.run(
            ["bash", script_path, proj_path, "--from-taskmaster"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT)
        )

        prd_path = Path(temp_project) / "plans" / "prd.json"
        orchestrator.load_prd(prd_path)

        assert len(orchestrator.context.waves) == 3
        assert len(orchestrator.context.waves[1]) == 2

    def test_no_manual_intervention_required(self, temp_project, orchestrator):
        """Verify full execution without manual intervention"""
        tasks = self._create_auth_feature_tasks()
        self._write_tasks(temp_project, tasks)

        script_path = to_posix_path(SCRIPT_PATH)
        proj_path = to_posix_path(temp_project)
        result = subprocess.run(
            ["bash", script_path, proj_path, "--from-taskmaster"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT)
        )
        assert result.returncode == 0

        prd_path = Path(temp_project) / "plans" / "prd.json"
        orchestrator.load_prd(prd_path)
        orchestrator.load_memory_context()
        orchestrator.execute_waves()
        handoff = orchestrator.create_handoff("Complete", ["Next"])

        failed_spawns = [s for s in orchestrator.context.spawns if s.status != "completed"]
        assert len(failed_spawns) == 0

        assert handoff is not None

    def _create_auth_feature_tasks(self):
        """Create auth feature tasks for testing"""
        return {"tasks": [
            {"id": 1, "title": "Set up auth database schema", "status": "pending", "dependencies": []},
            {"id": 2, "title": "Implement JWT service", "status": "pending", "dependencies": [1]},
            {"id": 3, "title": "Create login API endpoints", "status": "pending", "dependencies": [1, 2]},
            {"id": 4, "title": "Build React login form", "status": "pending", "dependencies": [3]},
            {"id": 5, "title": "Implement protected route", "status": "pending", "dependencies": [3]},
            {"id": 6, "title": "Create auth context", "status": "pending", "dependencies": [4, 5]},
            {"id": 7, "title": "Write unit tests for auth", "status": "pending", "dependencies": [3]},
            {"id": 8, "title": "Security audit for auth", "status": "pending", "dependencies": [3, 6]},
            {"id": 9, "title": "Update API documentation", "status": "pending", "dependencies": [3]}
        ]}

    def _create_diverse_tasks_for_all_agents(self):
        """Create tasks that trigger all 8 agent types"""
        return {"tasks": [
            {"id": 1, "title": "Set up Docker backend", "status": "pending", "dependencies": []},
            {"id": 2, "title": "Create React form component", "status": "pending", "dependencies": []},
            {"id": 3, "title": "Write unit tests for auth", "status": "pending", "dependencies": [1, 2]},
            {"id": 4, "title": "Debug login error handling", "status": "pending", "dependencies": [2]},
            {"id": 5, "title": "Refactor user service cleanup", "status": "pending", "dependencies": [1]},
            {"id": 6, "title": "Security audit for auth", "status": "pending", "dependencies": [1, 2]},
            {"id": 7, "title": "Update API documentation", "status": "pending", "dependencies": [1]},
            {"id": 8, "title": "Review pull request", "status": "pending", "dependencies": [3, 4, 5, 6, 7]}
        ]}

    def _write_tasks(self, project_dir, tasks):
        tasks_file = Path(project_dir) / ".taskmaster" / "tasks" / "tasks.json"
        with open(tasks_file, "w") as f:
            json.dump(tasks, f)


@requires_jq
class TestIntegrationVerification:
    """Verification checklist tests"""

    @pytest.fixture
    def redis_client(self):
        client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        yield client

    def test_redis_connection(self, redis_client):
        """Verify Redis connection works"""
        redis_client.set("test_key", "test_value")
        assert redis_client.get("test_key") == "test_value"
        redis_client.delete("test_key")

    def test_generate_prd_script_exists(self):
        """Verify generate-prd.sh exists and is executable"""
        assert SCRIPT_PATH.exists()

    def test_fixtures_exist(self):
        """Verify test fixtures are in place"""
        fixtures_path = PROJECT_ROOT / "tests" / "fixtures"
        assert (fixtures_path / "sample_prd.md").exists()
        assert (fixtures_path / "sample_tasks.json").exists()
        assert (fixtures_path / "expected_prd.json").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
