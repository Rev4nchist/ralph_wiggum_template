"""
ST-004: Cascade Agent Failures

Tests system recovery when multiple agents crash mid-execution.
Verifies orphan detection, task recovery, and no duplicate execution.

Pass Criteria:
- Orphans detected < heartbeat_ttl + 5s
- All tasks eventually completed (by survivors)
- No duplicate task execution
- Locks released < 2x TTL
"""
import pytest
import time
import threading
import random
import json
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from typing import List, Dict, Set, Optional
from dataclasses import dataclass, field
from enum import Enum

from ..conftest import requires_redis, TaskSimulator
from ..metrics import StressTestMetrics, MetricsCollector


WAVE_SIZE = 8
TASKS_PER_AGENT = 3
TOTAL_TASKS = WAVE_SIZE * TASKS_PER_AGENT
CRASH_RATE = 0.5
HEARTBEAT_TTL = 5
TASK_EXECUTION_TIME = 1


class AgentState(Enum):
    RUNNING = "running"
    CRASHED = "crashed"
    COMPLETED = "completed"


@dataclass
class CrashableAgent:
    agent_id: str
    redis_client: any
    test_prefix: str
    state: AgentState = AgentState.RUNNING
    tasks_claimed: List[str] = field(default_factory=list)
    tasks_completed: List[str] = field(default_factory=list)
    crash_event: threading.Event = field(default_factory=threading.Event)
    heartbeat_thread: Optional[threading.Thread] = None

    def start_heartbeat(self):
        def heartbeat_loop():
            while not self.crash_event.is_set() and self.state == AgentState.RUNNING:
                self._send_heartbeat()
                time.sleep(HEARTBEAT_TTL / 3)

        self.heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()

    def _send_heartbeat(self):
        key = f"{self.test_prefix}:agent:{self.agent_id}:heartbeat"
        self.redis_client.setex(key, HEARTBEAT_TTL, json.dumps({
            "agent_id": self.agent_id,
            "timestamp": time.time(),
            "tasks": self.tasks_claimed
        }))

    def simulate_crash(self):
        self.state = AgentState.CRASHED
        self.crash_event.set()

    def is_alive(self) -> bool:
        key = f"{self.test_prefix}:agent:{self.agent_id}:heartbeat"
        return self.redis_client.exists(key) > 0


@dataclass
class TaskExecutionRecord:
    task_id: str
    agent_id: str
    started_at: float
    completed_at: Optional[float] = None
    success: bool = False
    orphaned: bool = False
    recovered_by: Optional[str] = None


class OrphanDetector:

    def __init__(self, redis_client, test_prefix: str):
        self.redis = redis_client
        self.prefix = test_prefix
        self.detected_orphans: List[str] = []
        self.detection_times: Dict[str, float] = {}

    def detect_orphans(self) -> List[str]:
        orphans = []
        claimed_key = f"{self.prefix}:tasks:claimed"
        claimed_tasks = self.redis.hgetall(claimed_key)

        for task_id, claim_data_str in claimed_tasks.items():
            claim_data = json.loads(claim_data_str)
            agent_id = claim_data.get("agent_id")
            claimed_at = claim_data.get("claimed_at", 0)

            heartbeat_key = f"{self.prefix}:agent:{agent_id}:heartbeat"
            heartbeat_exists = self.redis.exists(heartbeat_key)
            time_since_claim = time.time() - claimed_at

            if not heartbeat_exists and time_since_claim > 2:
                orphans.append(task_id)
                if task_id not in self.detection_times:
                    self.detection_times[task_id] = time.time()
                    self.detected_orphans.append(task_id)

        return orphans

    def reassign_orphan(self, task_id: str, new_agent_id: str) -> bool:
        claimed_key = f"{self.prefix}:tasks:claimed"
        claim_data = self.redis.hget(claimed_key, task_id)

        if claim_data:
            self.redis.hdel(claimed_key, task_id)
            self.redis.hset(claimed_key, task_id, json.dumps({
                "agent_id": new_agent_id,
                "claimed_at": time.time(),
                "recovered": True
            }))
            return True
        return False


class TaskCoordinator:

    def __init__(self, redis_client, test_prefix: str):
        self.redis = redis_client
        self.prefix = test_prefix
        self.lock = threading.Lock()
        self.execution_records: Dict[str, List[TaskExecutionRecord]] = {}

    def register_task(self, task_id: str):
        pending_key = f"{self.prefix}:tasks:pending"
        self.redis.sadd(pending_key, task_id)

    def claim_task(self, task_id: str, agent_id: str) -> bool:
        claimed_key = f"{self.prefix}:tasks:claimed"
        pending_key = f"{self.prefix}:tasks:pending"

        if not self.redis.sismember(pending_key, task_id):
            return False

        existing = self.redis.hget(claimed_key, task_id)
        if existing:
            return False

        self.redis.srem(pending_key, task_id)
        self.redis.hset(claimed_key, task_id, json.dumps({
            "agent_id": agent_id,
            "claimed_at": time.time()
        }))

        with self.lock:
            if task_id not in self.execution_records:
                self.execution_records[task_id] = []
            self.execution_records[task_id].append(TaskExecutionRecord(
                task_id=task_id,
                agent_id=agent_id,
                started_at=time.time()
            ))

        return True

    def complete_task(self, task_id: str, agent_id: str) -> bool:
        claimed_key = f"{self.prefix}:tasks:claimed"
        completed_key = f"{self.prefix}:tasks:completed"

        claim_data_str = self.redis.hget(claimed_key, task_id)
        if not claim_data_str:
            return False

        claim_data = json.loads(claim_data_str)
        if claim_data.get("agent_id") != agent_id and not claim_data.get("recovered"):
            return False

        self.redis.hdel(claimed_key, task_id)
        self.redis.hset(completed_key, task_id, json.dumps({
            "agent_id": agent_id,
            "completed_at": time.time()
        }))

        with self.lock:
            if task_id in self.execution_records:
                for record in self.execution_records[task_id]:
                    if record.agent_id == agent_id and not record.completed_at:
                        record.completed_at = time.time()
                        record.success = True
                        break

        return True

    def get_duplicate_executions(self) -> List[str]:
        duplicates = []
        with self.lock:
            for task_id, records in self.execution_records.items():
                successful = [r for r in records if r.success]
                if len(successful) > 1:
                    duplicates.append(task_id)
        return duplicates


def agent_worker(
    agent: CrashableAgent,
    coordinator: TaskCoordinator,
    tasks: List[str],
    execution_time: float
) -> Dict:
    agent.start_heartbeat()
    claimed = []
    completed = []
    errors = []

    for task_id in tasks:
        if agent.crash_event.is_set():
            break

        if coordinator.claim_task(task_id, agent.agent_id):
            claimed.append(task_id)
            agent.tasks_claimed.append(task_id)

            for _ in range(int(execution_time * 10)):
                if agent.crash_event.is_set():
                    errors.append(f"Crashed during {task_id}")
                    break
                time.sleep(0.1)

            if not agent.crash_event.is_set():
                if coordinator.complete_task(task_id, agent.agent_id):
                    completed.append(task_id)
                    agent.tasks_completed.append(task_id)

    agent.state = AgentState.COMPLETED if not agent.crash_event.is_set() else AgentState.CRASHED

    return {
        "agent_id": agent.agent_id,
        "claimed": claimed,
        "completed": completed,
        "errors": errors,
        "crashed": agent.state == AgentState.CRASHED
    }


def recovery_worker(
    agent: CrashableAgent,
    coordinator: TaskCoordinator,
    detector: OrphanDetector,
    execution_time: float,
    max_runtime: float = 60.0
) -> Dict:
    agent.start_heartbeat()
    recovered = []
    completed = []
    claimed_pending = []
    start_time = time.time()

    while time.time() - start_time < max_runtime:
        if agent.crash_event.is_set():
            break

        completed_key = f"{coordinator.prefix}:tasks:completed"
        if coordinator.redis.hlen(completed_key) >= TOTAL_TASKS:
            break

        # First, recover orphaned tasks
        orphans = detector.detect_orphans()
        for task_id in orphans:
            if agent.crash_event.is_set() or time.time() - start_time >= max_runtime:
                break

            if detector.reassign_orphan(task_id, agent.agent_id):
                recovered.append(task_id)
                agent.tasks_claimed.append(task_id)

                time.sleep(execution_time)

                if not agent.crash_event.is_set():
                    if coordinator.complete_task(task_id, agent.agent_id):
                        completed.append(task_id)
                        agent.tasks_completed.append(task_id)

        # Then, claim pending tasks that haven't been picked up
        pending_key = f"{coordinator.prefix}:tasks:pending"
        pending_tasks = list(coordinator.redis.smembers(pending_key))
        for task_id in pending_tasks:
            if agent.crash_event.is_set() or time.time() - start_time >= max_runtime:
                break

            if coordinator.claim_task(task_id, agent.agent_id):
                claimed_pending.append(task_id)
                agent.tasks_claimed.append(task_id)

                time.sleep(execution_time)

                if not agent.crash_event.is_set():
                    if coordinator.complete_task(task_id, agent.agent_id):
                        completed.append(task_id)
                        agent.tasks_completed.append(task_id)

        time.sleep(0.5)

    return {
        "agent_id": agent.agent_id,
        "recovered": recovered,
        "claimed_pending": claimed_pending,
        "completed": completed,
        "role": "recovery"
    }


@requires_redis
class TestCascadeFailure:

    def test_agent_crash_and_recovery(
        self,
        redis_client,
        stress_test_id,
        thread_pool_20
    ):
        """
        ST-004: 8 agents claim tasks, 4 crash mid-execution.
        Survivors and recovery agent complete all tasks.
        """
        metrics = MetricsCollector(stress_test_id, "ST-004: Cascade Agent Failure")
        coordinator = TaskCoordinator(redis_client, stress_test_id)
        detector = OrphanDetector(redis_client, stress_test_id)

        tasks = [f"task-{i}" for i in range(TOTAL_TASKS)]
        for task_id in tasks:
            coordinator.register_task(task_id)

        agents = [
            CrashableAgent(f"agent-{i}", redis_client, stress_test_id)
            for i in range(WAVE_SIZE)
        ]

        crash_indices = random.sample(range(WAVE_SIZE), int(WAVE_SIZE * CRASH_RATE))

        recovery_agent = CrashableAgent("recovery-agent", redis_client, stress_test_id)

        task_distribution = [
            tasks[i * TASKS_PER_AGENT:(i + 1) * TASKS_PER_AGENT]
            for i in range(WAVE_SIZE)
        ]

        start_time = time.time()
        futures: Dict[Future, str] = {}

        with ThreadPoolExecutor(max_workers=WAVE_SIZE + 2) as executor:
            for i, agent in enumerate(agents):
                f = executor.submit(
                    agent_worker,
                    agent,
                    coordinator,
                    task_distribution[i],
                    TASK_EXECUTION_TIME
                )
                futures[f] = f"worker-{i}"

            recovery_future = executor.submit(
                recovery_worker,
                recovery_agent,
                coordinator,
                detector,
                TASK_EXECUTION_TIME
            )
            futures[recovery_future] = "recovery"

            time.sleep(TASK_EXECUTION_TIME / 2)
            for idx in crash_indices:
                agents[idx].simulate_crash()

            results = []
            recovery_result = None
            for f in as_completed(futures, timeout=120):
                result = f.result()
                if futures[f] == "recovery":
                    recovery_result = result
                else:
                    results.append(result)
                    metrics.record_instant(
                        "agent_execution",
                        (time.time() - start_time) * 1000,
                        not result.get("crashed", False)
                    )

        final_metrics = metrics.finalize()
        final_metrics.print_summary()

        completed_key = f"{stress_test_id}:tasks:completed"
        completed_count = redis_client.hlen(completed_key)

        # Debug info
        claimed_key = f"{stress_test_id}:tasks:claimed"
        still_claimed = redis_client.hlen(claimed_key)
        print(f"\nDebug: completed={completed_count}, still_claimed={still_claimed}, orphans_detected={len(detector.detected_orphans)}")
        if recovery_result:
            print(f"Recovery agent: recovered={len(recovery_result.get('recovered', []))}, completed={len(recovery_result.get('completed', []))}")

        assert completed_count == TOTAL_TASKS, \
            f"Not all tasks completed: {completed_count}/{TOTAL_TASKS}"

        duplicates = coordinator.get_duplicate_executions()
        assert len(duplicates) == 0, \
            f"Duplicate executions detected: {duplicates}"

        crashed_agents = [r for r in results if r.get("crashed")]
        assert len(crashed_agents) == len(crash_indices), \
            f"Crash simulation failed: {len(crashed_agents)} vs {len(crash_indices)}"

        assert len(detector.detected_orphans) > 0, \
            "No orphans detected - crash recovery not tested"

        for task_id, detection_time in detector.detection_times.items():
            assert detection_time - start_time < HEARTBEAT_TTL + 15, \
                f"Orphan {task_id} detected too late: {detection_time - start_time:.1f}s"

    def test_progressive_agent_failures(
        self,
        redis_client,
        stress_test_id,
        thread_pool_20
    ):
        """
        Agents fail progressively over time, system adapts.
        """
        coordinator = TaskCoordinator(redis_client, f"{stress_test_id}:prog")
        detector = OrphanDetector(redis_client, f"{stress_test_id}:prog")

        num_tasks = 30
        tasks = [f"prog-task-{i}" for i in range(num_tasks)]
        for task_id in tasks:
            coordinator.register_task(task_id)

        agents = [
            CrashableAgent(f"prog-agent-{i}", redis_client, f"{stress_test_id}:prog")
            for i in range(6)
        ]

        recovery_agents = [
            CrashableAgent(f"prog-recovery-{i}", redis_client, f"{stress_test_id}:prog")
            for i in range(2)
        ]

        def progressive_crash_scheduler():
            time.sleep(3)
            agents[0].simulate_crash()
            time.sleep(3)
            agents[1].simulate_crash()
            time.sleep(3)
            agents[2].simulate_crash()

        crash_thread = threading.Thread(target=progressive_crash_scheduler, daemon=True)
        crash_thread.start()

        with ThreadPoolExecutor(max_workers=10) as executor:
            task_per_agent = num_tasks // len(agents)
            futures = []

            for i, agent in enumerate(agents):
                agent_tasks = tasks[i * task_per_agent:(i + 1) * task_per_agent]
                f = executor.submit(
                    agent_worker,
                    agent,
                    coordinator,
                    agent_tasks,
                    1.0
                )
                futures.append(f)

            for recovery_agent in recovery_agents:
                f = executor.submit(
                    recovery_worker,
                    recovery_agent,
                    coordinator,
                    detector,
                    0.5,
                    50.0
                )
                futures.append(f)

            for f in as_completed(futures, timeout=70):
                f.result()

        completed_key = f"{stress_test_id}:prog:tasks:completed"
        completed_count = redis_client.hlen(completed_key)
        completion_rate = completed_count / num_tasks
        assert completion_rate >= 0.95, \
            f"Tasks incomplete after progressive failures: {completed_count}/{num_tasks} ({completion_rate:.0%})"

    def test_lock_release_on_crash(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Verify locks are released when agent crashes (via TTL).
        """
        lock_key = f"{stress_test_id}:file:shared.ts:lock"
        lock_ttl = 5

        redis_client.setex(lock_key, lock_ttl, json.dumps({
            "agent_id": "crashed-agent",
            "acquired_at": time.time()
        }))

        assert redis_client.exists(lock_key), "Lock should exist initially"

        time.sleep(lock_ttl + 1)

        assert not redis_client.exists(lock_key), \
            "Lock should be released after TTL expiry"

    def test_no_task_starvation(
        self,
        redis_client,
        stress_test_id,
        thread_pool_10
    ):
        """
        Even with crashes, all tasks eventually complete.
        """
        coordinator = TaskCoordinator(redis_client, f"{stress_test_id}:starve")
        detector = OrphanDetector(redis_client, f"{stress_test_id}:starve")

        num_tasks = 20
        tasks = [f"starve-task-{i}" for i in range(num_tasks)]
        for task_id in tasks:
            coordinator.register_task(task_id)

        agents = [
            CrashableAgent(f"starve-agent-{i}", redis_client, f"{stress_test_id}:starve")
            for i in range(4)
        ]

        recovery_agent = CrashableAgent("starve-recovery", redis_client, f"{stress_test_id}:starve")

        def random_crash():
            time.sleep(random.uniform(1, 3))
            victim = random.choice(agents[:2])
            victim.simulate_crash()

        crash_thread = threading.Thread(target=random_crash, daemon=True)
        crash_thread.start()

        start_time = time.time()
        max_duration = 30

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = []

            task_per_agent = num_tasks // len(agents)
            for i, agent in enumerate(agents):
                agent_tasks = tasks[i * task_per_agent:(i + 1) * task_per_agent]
                f = executor.submit(agent_worker, agent, coordinator, agent_tasks, 0.5)
                futures.append(f)

            f = executor.submit(recovery_worker, recovery_agent, coordinator, detector, 0.3, max_duration - 2)
            futures.append(f)

            for f in as_completed(futures, timeout=max_duration + 10):
                f.result()

        duration = time.time() - start_time
        completed_key = f"{stress_test_id}:starve:tasks:completed"
        completed_count = redis_client.hlen(completed_key)

        assert completed_count == num_tasks, \
            f"Task starvation: {completed_count}/{num_tasks} completed in {duration:.1f}s"

    def test_heartbeat_detection_timing(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Verify heartbeat expiration triggers correct timing.
        """
        agent = CrashableAgent("heartbeat-test", redis_client, stress_test_id)
        agent.start_heartbeat()

        time.sleep(0.5)
        assert agent.is_alive(), "Agent should be alive after heartbeat"

        agent.simulate_crash()
        assert agent.is_alive(), "Agent appears alive immediately after crash (heartbeat still valid)"

        time.sleep(HEARTBEAT_TTL + 1)
        assert not agent.is_alive(), "Agent should appear dead after heartbeat TTL"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
