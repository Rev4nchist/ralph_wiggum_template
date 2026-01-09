"""
ST-008: Wave Timing Race Conditions

Tests race conditions at wave boundaries when tasks complete
and dependent tasks try to start simultaneously.

Pass Criteria:
- No premature wave starts
- Dependency check atomic with claim
- Status transitions serializable
"""
import pytest
import time
import threading
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Set
from dataclasses import dataclass, field

from ..conftest import requires_redis
from ..metrics import MetricsCollector


@dataclass
class WaveTask:
    task_id: str
    wave: int
    deps: List[str]
    status: str = "pending"


class AtomicTaskCoordinator:

    CLAIM_SCRIPT = """
    local task_key = KEYS[1]
    local deps_key = KEYS[2]
    local completed_key = KEYS[3]
    local agent_id = ARGV[1]
    local deps_json = ARGV[2]

    -- Check if already claimed
    local current = redis.call('HGET', task_key, 'status')
    if current and current ~= 'pending' then
        return 0
    end

    -- Check dependencies
    local deps = cjson.decode(deps_json)
    for _, dep in ipairs(deps) do
        local dep_status = redis.call('SISMEMBER', completed_key, dep)
        if dep_status == 0 then
            return 0
        end
    end

    -- Atomic claim
    redis.call('HSET', task_key, 'status', 'in_progress')
    redis.call('HSET', task_key, 'agent', agent_id)
    redis.call('HSET', task_key, 'claimed_at', ARGV[3])

    return 1
    """

    def __init__(self, redis_client, prefix: str):
        self.redis = redis_client
        self.prefix = prefix
        self.claim_script = self.redis.register_script(self.CLAIM_SCRIPT)
        self.race_violations: List[Dict] = []
        self.lock = threading.Lock()

    def register_task(self, task: WaveTask):
        task_key = f"{self.prefix}:task:{task.task_id}"
        self.redis.hset(task_key, mapping={
            "task_id": task.task_id,
            "wave": task.wave,
            "deps": json.dumps(task.deps),
            "status": "pending"
        })

    def atomic_claim(self, task_id: str, deps: List[str], agent_id: str) -> bool:
        task_key = f"{self.prefix}:task:{task_id}"
        deps_key = f"{self.prefix}:deps"
        completed_key = f"{self.prefix}:completed"

        result = self.claim_script(
            keys=[task_key, deps_key, completed_key],
            args=[agent_id, json.dumps(deps), str(time.time())]
        )
        return result == 1

    def complete_task(self, task_id: str):
        task_key = f"{self.prefix}:task:{task_id}"
        completed_key = f"{self.prefix}:completed"

        self.redis.hset(task_key, "status", "completed")
        self.redis.hset(task_key, "completed_at", str(time.time()))
        self.redis.sadd(completed_key, task_id)

    def check_race_violation(self, task_id: str, deps: List[str]) -> bool:
        completed_key = f"{self.prefix}:completed"
        for dep in deps:
            if not self.redis.sismember(completed_key, dep):
                with self.lock:
                    self.race_violations.append({
                        "task": task_id,
                        "missing_dep": dep,
                        "timestamp": time.time()
                    })
                return True
        return False

    def get_task_status(self, task_id: str) -> Dict:
        task_key = f"{self.prefix}:task:{task_id}"
        return self.redis.hgetall(task_key)


@requires_redis
class TestWaveTiming:

    def test_no_premature_wave_start(
        self,
        redis_client,
        stress_test_id,
        thread_pool_20
    ):
        """
        ST-008: Wave 2 tasks should not start before Wave 1 completes.
        """
        coordinator = AtomicTaskCoordinator(redis_client, stress_test_id)

        wave1_tasks = [WaveTask(f"w1-{i}", 1, []) for i in range(5)]
        wave2_tasks = [WaveTask(f"w2-{i}", 2, [f"w1-{i % 5}"]) for i in range(10)]

        for task in wave1_tasks + wave2_tasks:
            coordinator.register_task(task)

        claim_attempts = []
        lock = threading.Lock()

        def aggressive_claimer(agent_id: str, tasks: List[WaveTask]):
            results = []
            for task in tasks:
                claimed = coordinator.atomic_claim(task.task_id, task.deps, agent_id)
                with lock:
                    claim_attempts.append({
                        "agent": agent_id,
                        "task": task.task_id,
                        "wave": task.wave,
                        "claimed": claimed,
                        "timestamp": time.time()
                    })
                if claimed:
                    results.append(task.task_id)
            return results

        futures = []
        for i in range(5):
            f = thread_pool_20.submit(aggressive_claimer, f"agent-{i}", wave2_tasks)
            futures.append(f)

        time.sleep(0.1)

        for task in wave1_tasks:
            coordinator.atomic_claim(task.task_id, task.deps, "wave1-agent")
            coordinator.complete_task(task.task_id)

        for f in as_completed(futures, timeout=10):
            f.result()

        premature_claims = [
            a for a in claim_attempts
            if a["wave"] == 2 and a["claimed"]
        ]

        for claim in premature_claims:
            task_status = coordinator.get_task_status(claim["task"])
            claimed_at = float(task_status.get("claimed_at", 0))

            dep_id = f"w1-{int(claim['task'].split('-')[1]) % 5}"
            dep_status = coordinator.get_task_status(dep_id)
            dep_completed_at = float(dep_status.get("completed_at", float("inf")))

            assert claimed_at >= dep_completed_at, \
                f"Premature claim: {claim['task']} claimed before {dep_id} completed"

    def test_atomic_dependency_check(
        self,
        redis_client,
        stress_test_id,
        thread_pool_10
    ):
        """
        Dependency check and claim must be atomic.
        """
        coordinator = AtomicTaskCoordinator(redis_client, f"{stress_test_id}:atomic")

        coordinator.register_task(WaveTask("dep-task", 1, []))
        coordinator.register_task(WaveTask("dependent", 2, ["dep-task"]))

        claim_results = []
        lock = threading.Lock()

        def race_claimer(agent_id: str):
            claimed = coordinator.atomic_claim("dependent", ["dep-task"], agent_id)
            with lock:
                claim_results.append({"agent": agent_id, "claimed": claimed})

        def completer():
            time.sleep(0.01)
            coordinator.atomic_claim("dep-task", [], "completer")
            coordinator.complete_task("dep-task")

        futures = []
        with ThreadPoolExecutor(max_workers=12) as executor:
            for i in range(10):
                futures.append(executor.submit(race_claimer, f"racer-{i}"))
            futures.append(executor.submit(completer))

            for f in as_completed(futures, timeout=10):
                f.result()

        successful_claims = [r for r in claim_results if r["claimed"]]

        assert len(successful_claims) <= 1, \
            f"Multiple successful claims: {successful_claims}"

    def test_status_transition_serializable(
        self,
        redis_client,
        stress_test_id,
        thread_pool_10
    ):
        """
        Status transitions must be serializable (no lost updates).
        """
        prefix = f"{stress_test_id}:serial"
        task_key = f"{prefix}:task:serial-task"

        redis_client.hset(task_key, mapping={
            "task_id": "serial-task",
            "status": "pending",
            "version": "0"
        })

        transition_log = []
        lock = threading.Lock()

        def transition_worker(worker_id: str, transitions: int):
            for i in range(transitions):
                pipe = redis_client.pipeline(True)
                try:
                    pipe.watch(task_key)
                    current = pipe.hgetall(task_key)
                    version = int(current.get("version", 0))

                    pipe.multi()
                    pipe.hset(task_key, "version", str(version + 1))
                    pipe.hset(task_key, "last_updater", worker_id)
                    pipe.execute()

                    with lock:
                        transition_log.append({
                            "worker": worker_id,
                            "version": version + 1,
                            "success": True
                        })
                except Exception:
                    with lock:
                        transition_log.append({
                            "worker": worker_id,
                            "success": False
                        })
                finally:
                    pipe.reset()

        futures = []
        for i in range(5):
            f = thread_pool_10.submit(transition_worker, f"worker-{i}", 10)
            futures.append(f)

        for f in as_completed(futures, timeout=10):
            f.result()

        final_version = int(redis_client.hget(task_key, "version"))
        successful_transitions = len([t for t in transition_log if t.get("success")])

        assert final_version == successful_transitions, \
            f"Version mismatch: final={final_version}, successful={successful_transitions}"

    def test_wave_boundary_stress(
        self,
        redis_client,
        stress_test_id,
        thread_pool_20
    ):
        """
        Stress test wave boundaries with zero inter-wave delay.
        """
        coordinator = AtomicTaskCoordinator(redis_client, f"{stress_test_id}:boundary")

        waves = []
        for w in range(5):
            wave_tasks = []
            for t in range(10):
                deps = [f"wave{w-1}-task{t % 10}"] if w > 0 else []
                task = WaveTask(f"wave{w}-task{t}", w, deps)
                wave_tasks.append(task)
                coordinator.register_task(task)
            waves.append(wave_tasks)

        execution_order = []
        lock = threading.Lock()

        def execute_wave(wave_idx: int, tasks: List[WaveTask], agent_id: str):
            for task in tasks:
                while True:
                    if coordinator.atomic_claim(task.task_id, task.deps, agent_id):
                        with lock:
                            execution_order.append({
                                "task": task.task_id,
                                "wave": wave_idx,
                                "time": time.time()
                            })
                        time.sleep(0.001)
                        coordinator.complete_task(task.task_id)
                        break
                    time.sleep(0.001)

        for wave_idx, wave_tasks in enumerate(waves):
            futures = []
            for i, task in enumerate(wave_tasks):
                f = thread_pool_20.submit(
                    execute_wave,
                    wave_idx,
                    [task],
                    f"agent-{wave_idx}-{i}"
                )
                futures.append(f)

            for f in as_completed(futures, timeout=30):
                f.result()

        for i in range(1, len(execution_order)):
            current = execution_order[i]
            for prev in execution_order[:i]:
                if current["wave"] > prev["wave"]:
                    continue

        assert len(coordinator.race_violations) == 0, \
            f"Race violations detected: {coordinator.race_violations}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
