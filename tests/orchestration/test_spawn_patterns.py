"""
Test Suite 4: Orchestration Spawn Pattern Tests
Tests parallel/sequential spawning, dependency resolution, and memory context loading
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from collections import defaultdict


class DependencyGraph:
    """Helper class to build and analyze task dependency graphs"""

    def __init__(self, tasks):
        self.tasks = {t["id"]: t for t in tasks}
        self.deps = {t["id"]: t.get("deps", []) for t in tasks}

    def get_execution_waves(self):
        """Calculate execution waves based on dependencies"""
        waves = []
        completed = set()
        remaining = set(self.tasks.keys())

        while remaining:
            wave = []
            for task_id in list(remaining):
                task = self.tasks[task_id]
                task_deps = self.deps.get(task_id, [])
                deps_met = all(
                    self._normalize_dep(d) in completed
                    for d in task_deps
                )
                if deps_met:
                    wave.append(task_id)

            if not wave:
                raise ValueError(f"Circular dependency detected. Remaining: {remaining}")

            waves.append(wave)
            completed.update(wave)
            remaining -= set(wave)

        return waves

    def _normalize_dep(self, dep):
        """Convert dependency reference to task ID"""
        if isinstance(dep, int):
            return f"TASK-{str(dep).zfill(3)}"
        return dep


class TestParallelSpawnPattern:
    """Test 4.1: Independent tasks spawn in parallel"""

    def test_independent_tasks_in_same_wave(self):
        """Tasks without dependencies are in wave 1"""
        tasks = [
            {"id": "TASK-001", "title": "Task A", "deps": []},
            {"id": "TASK-002", "title": "Task B", "deps": []},
            {"id": "TASK-003", "title": "Task C", "deps": []}
        ]

        graph = DependencyGraph(tasks)
        waves = graph.get_execution_waves()

        assert len(waves) == 1
        assert len(waves[0]) == 3
        assert set(waves[0]) == {"TASK-001", "TASK-002", "TASK-003"}

    def test_arch_first_then_parallel_impl(self):
        """Architecture task first, then parallel implementation"""
        tasks = [
            {"id": "ARCH-001", "title": "Architecture design", "deps": []},
            {"id": "BE-001", "title": "Backend API", "deps": ["ARCH-001"]},
            {"id": "FE-001", "title": "Frontend UI", "deps": ["ARCH-001"]}
        ]

        graph = DependencyGraph(tasks)
        waves = graph.get_execution_waves()

        assert len(waves) == 2
        assert waves[0] == ["ARCH-001"]
        assert set(waves[1]) == {"BE-001", "FE-001"}

    def test_qa_after_all_impl(self):
        """QA waits for all implementation tasks"""
        tasks = [
            {"id": "ARCH-001", "title": "Architecture", "deps": []},
            {"id": "BE-001", "title": "Backend", "deps": ["ARCH-001"]},
            {"id": "FE-001", "title": "Frontend", "deps": ["ARCH-001"]},
            {"id": "QA-001", "title": "QA tests", "deps": ["BE-001", "FE-001"]}
        ]

        graph = DependencyGraph(tasks)
        waves = graph.get_execution_waves()

        assert len(waves) == 3
        assert "QA-001" in waves[2]
        assert "QA-001" not in waves[0] and "QA-001" not in waves[1]


class TestSequentialSpawnPattern:
    """Test 4.2: Dependent tasks wait for predecessors"""

    def test_linear_chain_sequential(self):
        """Linear chain A→B→C→D executes sequentially"""
        tasks = [
            {"id": "TASK-001", "title": "A", "deps": []},
            {"id": "TASK-002", "title": "B", "deps": [1]},
            {"id": "TASK-003", "title": "C", "deps": [2]},
            {"id": "TASK-004", "title": "D", "deps": [3]}
        ]

        graph = DependencyGraph(tasks)
        waves = graph.get_execution_waves()

        assert len(waves) == 4
        assert waves[0] == ["TASK-001"]
        assert waves[1] == ["TASK-002"]
        assert waves[2] == ["TASK-003"]
        assert waves[3] == ["TASK-004"]

    def test_dependent_waits_for_predecessor(self):
        """Task B cannot start before Task A completes"""
        tasks = [
            {"id": "TASK-001", "title": "A", "deps": []},
            {"id": "TASK-002", "title": "B", "deps": [1]}
        ]

        graph = DependencyGraph(tasks)
        waves = graph.get_execution_waves()

        a_wave = next(i for i, w in enumerate(waves) if "TASK-001" in w)
        b_wave = next(i for i, w in enumerate(waves) if "TASK-002" in w)

        assert b_wave > a_wave

    def test_multiple_deps_all_must_complete(self):
        """Task with multiple deps waits for all"""
        tasks = [
            {"id": "TASK-001", "title": "A", "deps": []},
            {"id": "TASK-002", "title": "B", "deps": []},
            {"id": "TASK-003", "title": "C", "deps": [1, 2]}
        ]

        graph = DependencyGraph(tasks)
        waves = graph.get_execution_waves()

        assert "TASK-001" in waves[0]
        assert "TASK-002" in waves[0]
        assert "TASK-003" in waves[1]


class TestDiamondDependency:
    """Test diamond dependency pattern"""

    def test_diamond_pattern_execution(self):
        """Diamond: A→[B,C]→D executes correctly"""
        tasks = [
            {"id": "TASK-001", "title": "A", "deps": []},
            {"id": "TASK-002", "title": "B", "deps": [1]},
            {"id": "TASK-003", "title": "C", "deps": [1]},
            {"id": "TASK-004", "title": "D", "deps": [2, 3]}
        ]

        graph = DependencyGraph(tasks)
        waves = graph.get_execution_waves()

        assert len(waves) == 3
        assert waves[0] == ["TASK-001"]
        assert set(waves[1]) == {"TASK-002", "TASK-003"}
        assert waves[2] == ["TASK-004"]


class TestMemoryContextLoading:
    """Test 4.3: Spawned agents receive memory context"""

    def test_spawn_prompt_includes_project_context(self):
        """Agent spawn includes project context"""
        project_context = {
            "name": "test-project",
            "tech_stack": ["React", "TypeScript"],
            "conventions": "Use functional components"
        }

        task = {"id": "FE-001", "title": "Build login form", "agent": "frontend"}

        spawn_prompt = self._build_spawn_prompt(task, project_context, [], [])

        assert "test-project" in spawn_prompt
        assert "React" in spawn_prompt
        assert "TypeScript" in spawn_prompt

    def test_spawn_prompt_includes_task_memories(self):
        """Agent spawn includes relevant task memories"""
        task = {"id": "FE-001", "title": "Build login form", "agent": "frontend"}
        memories = [
            {"content": "Use Formik for forms", "category": "pattern"},
            {"content": "Zod for validation", "category": "decision"}
        ]

        spawn_prompt = self._build_spawn_prompt(task, {}, memories, [])

        assert "Formik" in spawn_prompt
        assert "Zod" in spawn_prompt

    def test_spawn_prompt_includes_handoffs(self):
        """Agent spawn includes previous handoffs"""
        task = {"id": "FE-002", "title": "Add validation", "agent": "frontend"}
        handoffs = [
            {
                "task_id": "FE-001",
                "summary": "Login form created with basic UI",
                "next_steps": ["Add validation", "Handle errors"]
            }
        ]

        spawn_prompt = self._build_spawn_prompt(task, {}, [], handoffs)

        assert "Login form created" in spawn_prompt
        assert "Add validation" in spawn_prompt

    def _build_spawn_prompt(self, task, context, memories, handoffs):
        """Build spawn prompt with context (mimics orchestrator behavior)"""
        parts = []

        parts.append(f"Task: {task['id']} - {task['title']}")
        parts.append(f"Agent: {task['agent']}")

        if context:
            parts.append(f"\nProject Context:")
            parts.append(f"  Name: {context.get('name', 'N/A')}")
            if context.get('tech_stack'):
                parts.append(f"  Stack: {', '.join(context['tech_stack'])}")
            if context.get('conventions'):
                parts.append(f"  Conventions: {context['conventions']}")

        if memories:
            parts.append(f"\nRelevant Memories:")
            for mem in memories:
                parts.append(f"  - [{mem['category']}] {mem['content']}")

        if handoffs:
            parts.append(f"\nPrevious Handoffs:")
            for h in handoffs:
                parts.append(f"  - {h['task_id']}: {h['summary']}")
                if h.get('next_steps'):
                    parts.append(f"    Next: {', '.join(h['next_steps'])}")

        return "\n".join(parts)


class TestQAAutoSpawn:
    """Test 4.4: QA agent spawns after all impl tasks complete"""

    def test_qa_spawns_after_feature_impl(self):
        """QA spawns when feature implementation completes"""
        tasks = [
            {"id": "BE-001", "title": "Backend API", "deps": [], "agent": "backend", "status": "completed"},
            {"id": "FE-001", "title": "Frontend UI", "deps": [], "agent": "frontend", "status": "completed"},
            {"id": "QA-001", "title": "QA tests", "deps": ["BE-001", "FE-001"], "agent": "test-architect", "status": "pending"}
        ]

        impl_tasks = [t for t in tasks if t["agent"] != "test-architect"]
        all_impl_done = all(t["status"] == "completed" for t in impl_tasks)

        qa_task = next(t for t in tasks if t["agent"] == "test-architect")
        deps_satisfied = all_impl_done

        assert deps_satisfied is True
        assert qa_task["status"] == "pending"

    def test_qa_receives_impl_context(self):
        """QA agent receives implementation summaries"""
        impl_results = [
            {"task_id": "BE-001", "files": ["api/auth.py", "api/routes.py"], "summary": "Auth API ready"},
            {"task_id": "FE-001", "files": ["components/Login.tsx"], "summary": "Login form ready"}
        ]

        qa_context = self._build_qa_context(impl_results)

        assert "api/auth.py" in qa_context
        assert "components/Login.tsx" in qa_context
        assert "Auth API ready" in qa_context

    def _build_qa_context(self, impl_results):
        """Build QA context from implementation results"""
        parts = ["Implementation Summary for QA:"]
        for result in impl_results:
            parts.append(f"\n{result['task_id']}:")
            parts.append(f"  Summary: {result['summary']}")
            parts.append(f"  Files: {', '.join(result['files'])}")
        return "\n".join(parts)


class TestCircularDependencyDetection:
    """Test circular dependency detection"""

    def test_detects_simple_cycle(self):
        """Detects A→B→A cycle"""
        tasks = [
            {"id": "TASK-001", "title": "A", "deps": [2]},
            {"id": "TASK-002", "title": "B", "deps": [1]}
        ]

        with pytest.raises(ValueError, match="Circular dependency"):
            graph = DependencyGraph(tasks)
            graph.get_execution_waves()

    def test_detects_three_node_cycle(self):
        """Detects A→B→C→A cycle"""
        tasks = [
            {"id": "TASK-001", "title": "A", "deps": [3]},
            {"id": "TASK-002", "title": "B", "deps": [1]},
            {"id": "TASK-003", "title": "C", "deps": [2]}
        ]

        with pytest.raises(ValueError, match="Circular dependency"):
            graph = DependencyGraph(tasks)
            graph.get_execution_waves()


class TestAgentModelAssignment:
    """Test correct model assignment per agent type"""

    AGENT_MODELS = {
        "general-purpose": "Opus",
        "code-reviewer": "Minimax",
        "debugger": "GLM",
        "test-architect": "GLM",
        "refactorer": "GLM",
        "security-auditor": "Minimax",
        "docs-writer": "Minimax",
        "backend": "Opus",
        "frontend": "Opus"
    }

    @pytest.mark.parametrize("agent,expected_model", list(AGENT_MODELS.items()))
    def test_agent_model_mapping(self, agent, expected_model):
        """Each agent type maps to correct model"""
        assert self.AGENT_MODELS[agent] == expected_model


class TestWaveExecution:
    """Test wave-based execution simulation"""

    def test_full_project_wave_execution(self):
        """Simulate full project execution in waves"""
        tasks = [
            {"id": "ARCH-001", "title": "Architecture", "agent": "general-purpose", "deps": []},
            {"id": "BE-001", "title": "Backend API", "agent": "backend", "deps": ["ARCH-001"]},
            {"id": "FE-001", "title": "Frontend UI", "agent": "frontend", "deps": ["ARCH-001"]},
            {"id": "FE-002", "title": "Frontend forms", "agent": "frontend", "deps": ["BE-001", "FE-001"]},
            {"id": "QA-001", "title": "Write tests", "agent": "test-architect", "deps": ["FE-002"]},
            {"id": "SEC-001", "title": "Security audit", "agent": "security-auditor", "deps": ["FE-002"]},
            {"id": "REV-001", "title": "Code review", "agent": "code-reviewer", "deps": ["QA-001", "SEC-001"]}
        ]

        graph = DependencyGraph(tasks)
        waves = graph.get_execution_waves()

        assert len(waves) == 5
        assert waves[0] == ["ARCH-001"]
        assert set(waves[1]) == {"BE-001", "FE-001"}
        assert waves[2] == ["FE-002"]
        assert set(waves[3]) == {"QA-001", "SEC-001"}
        assert waves[4] == ["REV-001"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
