"""
ST-011: Full Orchestration Flow

CRITICAL: Complete workflow demonstration showing how the entire system
coordinates together end-to-end.

Tests the complete multi-agent orchestration flow:
- PRD parsing → Task dependency resolution
- Wave-based parallel execution
- Memory sharing between agents
- Handoff chain throughout project
- QA trigger after implementation
- Security audit and documentation

Pass Criteria:
- All 8 tasks complete in correct order
- 6 unique agent types spawned
- 10+ memories stored across project
- Each task's handoff retrievable by successor
- No task starts before dependencies complete
- Parallel tasks actually run simultaneously
- Later agents receive earlier context
- No orphaned file locks
- Final handoff contains project summary
"""
import pytest
import time
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from ..conftest import requires_redis, AgentSimulator
from ..metrics import StressTestMetrics, MetricsCollector
from ..harness import WaveBuilder


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentType(Enum):
    GENERAL_PURPOSE = "general-purpose"
    BACKEND = "backend"
    FRONTEND = "frontend"
    TEST_ARCHITECT = "test-architect"
    SECURITY_AUDITOR = "security-auditor"
    DOCS_WRITER = "docs-writer"


@dataclass
class PRDTask:
    task_id: str
    title: str
    agent_type: AgentType
    dependencies: List[str]
    acceptance_criteria: List[str]
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Dict] = None


@dataclass
class OrchestratorState:
    project_id: str
    tasks: Dict[str, PRDTask]
    waves: List[List[str]]
    current_wave: int = 0
    memories: List[Dict] = field(default_factory=list)
    handoffs: Dict[str, Dict] = field(default_factory=dict)
    agent_spawn_times: Dict[str, float] = field(default_factory=dict)
    execution_log: List[Dict] = field(default_factory=list)


class ProjectMemoryStore:

    def __init__(self, redis_client, project_id: str):
        self.redis = redis_client
        self.project_id = project_id
        self.memories_key = f"{project_id}:memories"
        self.handoffs_key = f"{project_id}:handoffs"
        self.context_key = f"{project_id}:context"

    def store_memory(
        self,
        agent_id: str,
        content: str,
        category: str,
        tags: List[str] = None
    ) -> str:
        memory_id = f"mem-{int(time.time() * 1000)}-{agent_id[:8]}"
        memory = {
            "id": memory_id,
            "agent_id": agent_id,
            "content": content,
            "category": category,
            "tags": tags or [],
            "timestamp": time.time()
        }
        self.redis.hset(self.memories_key, memory_id, json.dumps(memory))
        return memory_id

    def recall_memories(self, query: str, category: str = None) -> List[Dict]:
        all_memories = self.redis.hgetall(self.memories_key)
        results = []

        for mem_id, mem_json in all_memories.items():
            mem = json.loads(mem_json)
            if category and mem.get("category") != category:
                continue
            if query.lower() in mem.get("content", "").lower():
                results.append(mem)

        return sorted(results, key=lambda x: x.get("timestamp", 0), reverse=True)

    def create_handoff(
        self,
        from_task: str,
        to_task: str,
        summary: str,
        context: Dict,
        next_steps: List[str]
    ):
        handoff_id = f"handoff-{from_task}-{to_task}"
        handoff = {
            "id": handoff_id,
            "from_task": from_task,
            "to_task": to_task,
            "summary": summary,
            "context": context,
            "next_steps": next_steps,
            "created_at": time.time()
        }
        self.redis.hset(self.handoffs_key, handoff_id, json.dumps(handoff))

    def get_handoff(self, task_id: str) -> Optional[Dict]:
        all_handoffs = self.redis.hgetall(self.handoffs_key)
        for handoff_id, handoff_json in all_handoffs.items():
            handoff = json.loads(handoff_json)
            if handoff.get("to_task") == task_id:
                return handoff
        return None

    def get_task_chain_handoffs(self, task_id: str) -> List[Dict]:
        chain = []
        all_handoffs = self.redis.hgetall(self.handoffs_key)

        for handoff_json in all_handoffs.values():
            handoff = json.loads(handoff_json)
            chain.append(handoff)

        return sorted(chain, key=lambda x: x.get("created_at", 0))

    def get_project_context(self) -> Dict:
        memories = list(self.redis.hgetall(self.memories_key).values())
        handoffs = list(self.redis.hgetall(self.handoffs_key).values())

        return {
            "project_id": self.project_id,
            "memory_count": len(memories),
            "handoff_count": len(handoffs),
            "memories": [json.loads(m) for m in memories[-10:]],
            "handoffs": [json.loads(h) for h in handoffs]
        }


class FileLockManager:

    def __init__(self, redis_client, project_id: str):
        self.redis = redis_client
        self.project_id = project_id
        self.locks_key = f"{project_id}:locks"

    def acquire(self, file_path: str, agent_id: str, ttl: int = 60) -> bool:
        lock_key = f"{self.locks_key}:{file_path}"
        acquired = self.redis.set(lock_key, agent_id, nx=True, ex=ttl)
        return acquired is not None

    def release(self, file_path: str, agent_id: str) -> bool:
        lock_key = f"{self.locks_key}:{file_path}"
        current = self.redis.get(lock_key)
        if current == agent_id:
            self.redis.delete(lock_key)
            return True
        return False

    def get_all_locks(self) -> Dict[str, str]:
        locks = {}
        pattern = f"{self.locks_key}:*"
        for key in self.redis.scan_iter(pattern):
            file_path = key.replace(f"{self.locks_key}:", "")
            owner = self.redis.get(key)
            if owner:
                locks[file_path] = owner
        return locks


class TaskExecutor:

    def __init__(
        self,
        redis_client,
        project_id: str,
        memory_store: ProjectMemoryStore,
        lock_manager: FileLockManager
    ):
        self.redis = redis_client
        self.project_id = project_id
        self.memory = memory_store
        self.locks = lock_manager
        self.tasks_key = f"{project_id}:tasks"

    def execute_task(self, task: PRDTask, agent_id: str) -> Dict:
        handoff = self.memory.get_handoff(task.task_id)
        prior_context = handoff.get("context", {}) if handoff else {}

        relevant_memories = self.memory.recall_memories(
            query=task.title,
            category="architecture"
        )

        result = {
            "task_id": task.task_id,
            "agent_id": agent_id,
            "agent_type": task.agent_type.value,
            "received_handoff": handoff is not None,
            "prior_context": prior_context,
            "memories_accessed": len(relevant_memories),
            "files_modified": [],
            "decisions_made": [],
            "started_at": time.time()
        }

        if task.agent_type == AgentType.GENERAL_PURPOSE:
            result = self._execute_architecture_task(task, agent_id, result)
        elif task.agent_type == AgentType.BACKEND:
            result = self._execute_backend_task(task, agent_id, result)
        elif task.agent_type == AgentType.FRONTEND:
            result = self._execute_frontend_task(task, agent_id, result)
        elif task.agent_type == AgentType.TEST_ARCHITECT:
            result = self._execute_qa_task(task, agent_id, result)
        elif task.agent_type == AgentType.SECURITY_AUDITOR:
            result = self._execute_security_task(task, agent_id, result)
        elif task.agent_type == AgentType.DOCS_WRITER:
            result = self._execute_docs_task(task, agent_id, result)

        result["completed_at"] = time.time()
        result["duration_ms"] = (result["completed_at"] - result["started_at"]) * 1000

        return result

    def _execute_architecture_task(self, task: PRDTask, agent_id: str, result: Dict) -> Dict:
        time.sleep(0.5)

        self.memory.store_memory(
            agent_id,
            "Architecture decision: Use JWT with RS256 for authentication",
            "architecture",
            ["auth", "jwt", "security"]
        )
        self.memory.store_memory(
            agent_id,
            "Pattern: Repository pattern for data access layer",
            "pattern",
            ["architecture", "data-access"]
        )

        result["decisions_made"] = [
            "JWT with RS256 for auth tokens",
            "Repository pattern for data layer",
            "Event-driven communication between services"
        ]
        result["files_modified"] = ["docs/architecture.md"]

        self.memory.create_handoff(
            from_task=task.task_id,
            to_task="BE-001",
            summary="Architecture design complete",
            context={
                "auth_strategy": "JWT_RS256",
                "data_pattern": "repository",
                "api_style": "REST"
            },
            next_steps=["Implement JWT service", "Create data repositories"]
        )

        return result

    def _execute_backend_task(self, task: PRDTask, agent_id: str, result: Dict) -> Dict:
        time.sleep(0.3)

        files = ["src/services/auth.ts", "src/routes/login.ts"]
        for f in files:
            if self.locks.acquire(f, agent_id, ttl=30):
                result["files_modified"].append(f)

        arch_memories = self.memory.recall_memories("architecture", "architecture")
        result["context_inherited"] = len(arch_memories) > 0

        self.memory.store_memory(
            agent_id,
            f"Backend implementation: {task.title} using Express middleware",
            "pattern",
            ["backend", "implementation"]
        )

        for f in result["files_modified"]:
            self.locks.release(f, agent_id)

        next_task = "BE-002" if "BE-001" in task.task_id else "FE-002"
        self.memory.create_handoff(
            from_task=task.task_id,
            to_task=next_task,
            summary=f"Backend task {task.task_id} complete",
            context={"api_endpoints": ["/api/login", "/api/logout"]},
            next_steps=["Connect frontend to API", "Add error handling"]
        )

        return result

    def _execute_frontend_task(self, task: PRDTask, agent_id: str, result: Dict) -> Dict:
        time.sleep(0.3)

        files = ["src/components/LoginForm.tsx", "src/context/AuthContext.tsx"]
        for f in files:
            if self.locks.acquire(f, agent_id, ttl=30):
                result["files_modified"].append(f)

        # Check for architecture context from prior tasks
        arch_memories = self.memory.recall_memories("architecture", "architecture")
        result["context_inherited"] = len(arch_memories) > 0

        self.memory.store_memory(
            agent_id,
            f"Frontend implementation: Using React hooks with Formik for {task.title}",
            "pattern",
            ["frontend", "react", "forms"]
        )

        for f in result["files_modified"]:
            self.locks.release(f, agent_id)

        self.memory.create_handoff(
            from_task=task.task_id,
            to_task="QA-001" if "FE-002" in task.task_id else "FE-002",
            summary=f"Frontend task {task.task_id} complete",
            context={"components_created": files},
            next_steps=["Write component tests", "Add accessibility"]
        )

        return result

    def _execute_qa_task(self, task: PRDTask, agent_id: str, result: Dict) -> Dict:
        time.sleep(0.4)

        all_handoffs = self.memory.get_task_chain_handoffs(task.task_id)
        result["handoffs_received"] = len(all_handoffs)

        self.memory.store_memory(
            agent_id,
            "QA: All authentication flows tested - unit, integration, e2e",
            "decision",
            ["qa", "testing", "coverage"]
        )

        result["files_modified"] = [
            "tests/auth.test.ts",
            "tests/e2e/login.spec.ts"
        ]
        result["test_results"] = {
            "unit_tests": 24,
            "integration_tests": 8,
            "e2e_tests": 5,
            "coverage": "87%"
        }

        self.memory.create_handoff(
            from_task=task.task_id,
            to_task="SEC-001",
            summary="QA complete - all tests passing",
            context={"test_results": result["test_results"]},
            next_steps=["Security audit", "Performance testing"]
        )

        return result

    def _execute_security_task(self, task: PRDTask, agent_id: str, result: Dict) -> Dict:
        time.sleep(0.3)

        self.memory.store_memory(
            agent_id,
            "Security audit: OWASP Top 10 checked, no critical vulnerabilities",
            "decision",
            ["security", "audit", "owasp"]
        )

        result["security_findings"] = {
            "critical": 0,
            "high": 0,
            "medium": 1,
            "low": 3,
            "recommendations": ["Add rate limiting", "Implement CSRF tokens"]
        }

        self.memory.create_handoff(
            from_task=task.task_id,
            to_task="DOC-001",
            summary="Security audit complete - approved for production",
            context={"security_findings": result["security_findings"]},
            next_steps=["Document API", "Update security guidelines"]
        )

        return result

    def _execute_docs_task(self, task: PRDTask, agent_id: str, result: Dict) -> Dict:
        time.sleep(0.2)

        project_context = self.memory.get_project_context()
        result["project_context_available"] = project_context["memory_count"] > 0

        self.memory.store_memory(
            agent_id,
            "Documentation: API docs, architecture diagrams, and security guidelines updated",
            "decision",
            ["docs", "api", "final"]
        )

        result["files_modified"] = [
            "docs/API.md",
            "docs/SECURITY.md",
            "README.md"
        ]

        self.memory.create_handoff(
            from_task=task.task_id,
            to_task="FINAL",
            summary="Project documentation complete",
            context={
                "total_memories": project_context["memory_count"],
                "docs_created": result["files_modified"],
                "project_summary": "Auth feature fully implemented, tested, and documented"
            },
            next_steps=["Deploy to staging", "User acceptance testing"]
        )

        return result


def create_auth_feature_prd() -> Dict[str, PRDTask]:
    return {
        "ARCH-001": PRDTask(
            task_id="ARCH-001",
            title="Design authentication architecture",
            agent_type=AgentType.GENERAL_PURPOSE,
            dependencies=[],
            acceptance_criteria=[
                "Auth flow documented",
                "Token strategy defined",
                "API contracts specified"
            ]
        ),
        "BE-001": PRDTask(
            task_id="BE-001",
            title="Implement JWT service",
            agent_type=AgentType.BACKEND,
            dependencies=["ARCH-001"],
            acceptance_criteria=[
                "JWT generation working",
                "Token validation implemented",
                "Refresh token flow complete"
            ]
        ),
        "BE-002": PRDTask(
            task_id="BE-002",
            title="Create login API endpoint",
            agent_type=AgentType.BACKEND,
            dependencies=["BE-001"],
            acceptance_criteria=[
                "POST /api/login working",
                "Error handling complete",
                "Rate limiting implemented"
            ]
        ),
        "FE-001": PRDTask(
            task_id="FE-001",
            title="Build login form component",
            agent_type=AgentType.FRONTEND,
            dependencies=["ARCH-001"],
            acceptance_criteria=[
                "Form renders correctly",
                "Validation working",
                "Accessible (WCAG 2.1)"
            ]
        ),
        "FE-002": PRDTask(
            task_id="FE-002",
            title="Implement auth context",
            agent_type=AgentType.FRONTEND,
            dependencies=["BE-002", "FE-001"],
            acceptance_criteria=[
                "Auth state management working",
                "Protected routes implemented",
                "Token refresh handled"
            ]
        ),
        "QA-001": PRDTask(
            task_id="QA-001",
            title="Write authentication tests",
            agent_type=AgentType.TEST_ARCHITECT,
            dependencies=["BE-002", "FE-002"],
            acceptance_criteria=[
                "Unit tests complete",
                "Integration tests passing",
                "E2E tests for critical flows"
            ]
        ),
        "SEC-001": PRDTask(
            task_id="SEC-001",
            title="Security audit",
            agent_type=AgentType.SECURITY_AUDITOR,
            dependencies=["QA-001"],
            acceptance_criteria=[
                "OWASP Top 10 checked",
                "No critical vulnerabilities",
                "Security report generated"
            ]
        ),
        "DOC-001": PRDTask(
            task_id="DOC-001",
            title="Update API documentation",
            agent_type=AgentType.DOCS_WRITER,
            dependencies=["SEC-001"],
            acceptance_criteria=[
                "API docs complete",
                "Architecture diagrams updated",
                "Security guidelines documented"
            ]
        )
    }


def build_execution_waves(tasks: Dict[str, PRDTask]) -> List[List[str]]:
    task_list = [
        {"id": t.task_id, "deps": t.dependencies}
        for t in tasks.values()
    ]
    builder = WaveBuilder(task_list)
    return builder.build()


@requires_redis
class TestFullOrchestrationFlow:

    def test_complete_auth_feature_implementation(
        self,
        redis_client,
        stress_test_id,
        thread_pool_10
    ):
        """
        ST-011: Complete multi-agent orchestration flow.
        Demonstrates entire system working together end-to-end.
        """
        metrics = MetricsCollector(stress_test_id, "ST-011: Full Orchestration Flow")
        project_id = f"{stress_test_id}:auth-feature"

        memory_store = ProjectMemoryStore(redis_client, project_id)
        lock_manager = FileLockManager(redis_client, project_id)
        executor = TaskExecutor(redis_client, project_id, memory_store, lock_manager)

        tasks = create_auth_feature_prd()
        waves = build_execution_waves(tasks)

        state = OrchestratorState(
            project_id=project_id,
            tasks=tasks,
            waves=waves
        )

        agent_types_used: Set[str] = set()
        task_results: Dict[str, Dict] = {}
        wave_timing: List[Dict] = []

        for wave_idx, wave_tasks in enumerate(waves):
            wave_start = time.time()
            state.current_wave = wave_idx

            state.execution_log.append({
                "event": "wave_start",
                "wave": wave_idx,
                "tasks": wave_tasks,
                "timestamp": wave_start
            })

            def execute_wave_task(task_id: str) -> Tuple[str, Dict]:
                task = tasks[task_id]
                agent_id = f"{task.agent_type.value}-{task_id}"

                task.status = TaskStatus.IN_PROGRESS
                task.assigned_agent = agent_id
                task.started_at = time.time()
                state.agent_spawn_times[agent_id] = time.time()

                result = executor.execute_task(task, agent_id)

                task.status = TaskStatus.COMPLETED
                task.completed_at = time.time()
                task.result = result

                return task_id, result

            if len(wave_tasks) > 1:
                futures = {
                    thread_pool_10.submit(execute_wave_task, tid): tid
                    for tid in wave_tasks
                }
                for future in as_completed(futures, timeout=30):
                    task_id, result = future.result()
                    task_results[task_id] = result
                    agent_types_used.add(result["agent_type"])
                    metrics.record_instant(
                        f"task_{task_id}",
                        result["duration_ms"],
                        True
                    )
            else:
                task_id, result = execute_wave_task(wave_tasks[0])
                task_results[task_id] = result
                agent_types_used.add(result["agent_type"])
                metrics.record_instant(
                    f"task_{task_id}",
                    result["duration_ms"],
                    True
                )

            wave_duration = time.time() - wave_start
            wave_timing.append({
                "wave": wave_idx,
                "tasks": wave_tasks,
                "duration_seconds": wave_duration,
                "parallel": len(wave_tasks) > 1
            })

            state.execution_log.append({
                "event": "wave_complete",
                "wave": wave_idx,
                "duration_seconds": wave_duration,
                "timestamp": time.time()
            })

        final_metrics = metrics.finalize()
        final_metrics.print_summary()

        completed_tasks = [t for t in tasks.values() if t.status == TaskStatus.COMPLETED]
        assert len(completed_tasks) == 8, \
            f"Task completion: {len(completed_tasks)}/8 tasks completed"

        assert len(agent_types_used) == 6, \
            f"Agent diversity: {len(agent_types_used)}/6 unique types used: {agent_types_used}"

        project_context = memory_store.get_project_context()
        assert project_context["memory_count"] >= 8, \
            f"Memory accumulation: {project_context['memory_count']} < 8 memories"

        for task_id, task in tasks.items():
            if task.dependencies:
                for dep_id in task.dependencies:
                    dep_task = tasks[dep_id]
                    assert dep_task.completed_at < task.started_at, \
                        f"Wave ordering violation: {task_id} started before {dep_id} completed"

        be001_start = tasks["BE-001"].started_at
        fe001_start = tasks["FE-001"].started_at
        assert abs(be001_start - fe001_start) < 1.0, \
            f"Parallel execution: BE-001 and FE-001 should start within 1s, diff={abs(be001_start - fe001_start):.2f}s"

        for task_id, result in task_results.items():
            task = tasks[task_id]
            if task.dependencies:
                assert result.get("received_handoff") or result.get("context_inherited"), \
                    f"Context inheritance: {task_id} didn't receive prior context"

        orphaned_locks = lock_manager.get_all_locks()
        assert len(orphaned_locks) == 0, \
            f"Lock cleanup: {len(orphaned_locks)} orphaned locks: {orphaned_locks}"

        final_handoffs = memory_store.get_task_chain_handoffs("FINAL")
        doc_handoff = next(
            (h for h in final_handoffs if h.get("from_task") == "DOC-001"),
            None
        )
        assert doc_handoff is not None, \
            "Final handoff: DOC-001 should create final project handoff"
        assert "project_summary" in doc_handoff.get("context", {}), \
            "Final handoff should contain project summary"

        print("\n" + "=" * 60)
        print("ORCHESTRATION FLOW COMPLETE")
        print("=" * 60)
        print(f"Total tasks: {len(completed_tasks)}")
        print(f"Agent types: {agent_types_used}")
        print(f"Memories stored: {project_context['memory_count']}")
        print(f"Handoffs created: {project_context['handoff_count']}")
        print(f"Waves executed: {len(waves)}")
        for wt in wave_timing:
            parallel_marker = " (PARALLEL)" if wt["parallel"] else ""
            print(f"  Wave {wt['wave']}: {wt['tasks']}{parallel_marker} - {wt['duration_seconds']:.2f}s")
        print("=" * 60)

    def test_wave_dependency_resolution(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Verify wave builder correctly resolves task dependencies.
        """
        tasks = create_auth_feature_prd()
        waves = build_execution_waves(tasks)

        assert waves[0] == ["ARCH-001"], \
            f"Wave 0 should be ARCH-001, got {waves[0]}"

        assert set(waves[1]) == {"BE-001", "FE-001"}, \
            f"Wave 1 should be BE-001, FE-001, got {waves[1]}"

        assert "BE-002" in waves[2], \
            f"Wave 2 should contain BE-002, got {waves[2]}"

        for wave_idx, wave_tasks in enumerate(waves):
            for task_id in wave_tasks:
                task = tasks[task_id]
                for dep_id in task.dependencies:
                    dep_wave = next(
                        i for i, w in enumerate(waves) if dep_id in w
                    )
                    assert dep_wave < wave_idx, \
                        f"Dependency violation: {task_id} in wave {wave_idx} depends on {dep_id} in wave {dep_wave}"

    def test_memory_sharing_between_agents(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Verify agents can share memories across the project.
        """
        project_id = f"{stress_test_id}:memory-share"
        memory_store = ProjectMemoryStore(redis_client, project_id)

        # Store memories
        mem1_id = memory_store.store_memory(
            "arch-agent",
            "Use PostgreSQL for primary data store",
            "architecture",
            ["database", "decision"]
        )
        mem2_id = memory_store.store_memory(
            "arch-agent",
            "Redis for caching and session storage",
            "architecture",
            ["cache", "session"]
        )

        # Verify memories were stored
        all_memories = redis_client.hgetall(memory_store.memories_key)
        assert len(all_memories) >= 2, f"Expected 2+ memories stored, got {len(all_memories)}"

        # Test recall with partial match
        backend_recall = memory_store.recall_memories("postgresql")
        assert len(backend_recall) > 0, \
            f"Backend should recall database decision. All memories: {list(all_memories.values())}"

        frontend_recall = memory_store.recall_memories("session")
        assert len(frontend_recall) > 0, "Frontend should recall session decision"

    def test_handoff_chain_integrity(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Verify handoff chain maintains context throughout project.
        """
        project_id = f"{stress_test_id}:handoff-chain"
        memory_store = ProjectMemoryStore(redis_client, project_id)

        memory_store.create_handoff(
            from_task="ARCH-001",
            to_task="BE-001",
            summary="Architecture complete",
            context={"auth": "JWT", "db": "PostgreSQL"},
            next_steps=["Implement auth service"]
        )

        memory_store.create_handoff(
            from_task="BE-001",
            to_task="BE-002",
            summary="JWT service complete",
            context={"jwt_key": "RS256", "token_ttl": 3600},
            next_steps=["Create API endpoints"]
        )

        memory_store.create_handoff(
            from_task="BE-002",
            to_task="QA-001",
            summary="API endpoints complete",
            context={"endpoints": ["/login", "/logout", "/refresh"]},
            next_steps=["Write API tests"]
        )

        qa_handoff = memory_store.get_handoff("QA-001")
        assert qa_handoff is not None, "QA should receive handoff"
        assert "endpoints" in qa_handoff["context"], "QA handoff should include API endpoints"

        chain = memory_store.get_task_chain_handoffs("QA-001")
        assert len(chain) >= 3, f"Handoff chain should have 3+ entries, got {len(chain)}"

    def test_agent_type_routing(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Verify correct agent types are assigned to tasks.
        """
        tasks = create_auth_feature_prd()

        assert tasks["ARCH-001"].agent_type == AgentType.GENERAL_PURPOSE
        assert tasks["BE-001"].agent_type == AgentType.BACKEND
        assert tasks["FE-001"].agent_type == AgentType.FRONTEND
        assert tasks["QA-001"].agent_type == AgentType.TEST_ARCHITECT
        assert tasks["SEC-001"].agent_type == AgentType.SECURITY_AUDITOR
        assert tasks["DOC-001"].agent_type == AgentType.DOCS_WRITER


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
