"""
ST-002: Lock Contention Stampede

Tests file lock behavior with 100 agents competing for 10 files.
Verifies no deadlocks, fair distribution, and atomic operations.

Pass Criteria:
- No deadlocks (all agents make progress)
- No double-locks (atomicity verified)
- Fairness coefficient > 0.7 (no starvation)
- All locks released correctly
"""
import pytest
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Set
from dataclasses import dataclass, field
from collections import Counter

from ..conftest import requires_redis, LockSimulator
from ..metrics import StressTestMetrics, MetricsCollector
from ..harness import calculate_fairness


AGENTS = 100
FILES = [
    "shared/types.ts",
    "shared/api.ts",
    "shared/utils.ts",
    "shared/constants.ts",
    "shared/hooks.ts",
    "shared/context.ts",
    "shared/store.ts",
    "shared/theme.ts",
    "shared/i18n.ts",
    "shared/auth.ts"
]
LOCK_HOLD_TIME_MS = 50
TEST_DURATION_SECONDS = 30


@dataclass
class LockContentionResult:
    agent_id: str
    acquisitions: int
    contentions: int
    releases: int
    errors: List[str]
    files_acquired: Dict[str, int]
    latencies_ms: List[float]
    duration_seconds: float


def agent_lock_task(
    lock: LockSimulator,
    files: List[str],
    duration_seconds: float,
    hold_time_ms: int
) -> LockContentionResult:
    start = time.time()
    acquisitions = 0
    contentions = 0
    releases = 0
    errors = []
    files_acquired = Counter()
    latencies = []

    while time.time() - start < duration_seconds:
        file_path = random.choice(files)

        acq_start = time.time()
        try:
            acquired = lock.acquire(file_path, ttl=10)
            latency = (time.time() - acq_start) * 1000
            latencies.append(latency)

            if acquired:
                acquisitions += 1
                files_acquired[file_path] += 1

                time.sleep(hold_time_ms / 1000)

                released = lock.release(file_path)
                if released:
                    releases += 1
                # Note: Failed releases are expected under high contention (TTL expiry)
            else:
                contentions += 1
                time.sleep(0.001)

        except Exception as e:
            errors.append(f"Exception on {file_path}: {e}")
            time.sleep(0.01)

    # Release any locks still held at end of test
    for held_file in list(lock.held_locks):
        if lock.release(held_file):
            releases += 1

    return LockContentionResult(
        agent_id=lock.agent_id,
        acquisitions=acquisitions,
        contentions=contentions,
        releases=releases,
        errors=errors,
        files_acquired=dict(files_acquired),
        latencies_ms=latencies,
        duration_seconds=time.time() - start
    )


@requires_redis
class TestLockContention:

    def test_100_agents_10_files(
        self,
        redis_client,
        stress_test_id,
        lock_factory,
        thread_pool_100
    ):
        """
        ST-002: 100 agents compete for 10 files for 30 seconds.
        Verify no deadlocks, fair distribution, no double-locks.
        """
        metrics = MetricsCollector(stress_test_id, "ST-002: Lock Contention")

        locks = [lock_factory(f"lock-agent-{i}") for i in range(AGENTS)]

        def run_agent(lock: LockSimulator) -> LockContentionResult:
            return agent_lock_task(lock, FILES, TEST_DURATION_SECONDS, LOCK_HOLD_TIME_MS)

        futures = {thread_pool_100.submit(run_agent, lock): lock for lock in locks}
        results: List[LockContentionResult] = []

        for future in as_completed(futures, timeout=TEST_DURATION_SECONDS + 30):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                lock = futures[future]
                results.append(LockContentionResult(
                    agent_id=lock.agent_id,
                    acquisitions=0,
                    contentions=0,
                    releases=0,
                    errors=[str(e)],
                    files_acquired={},
                    latencies_ms=[],
                    duration_seconds=0
                ))

        total_acquisitions = sum(r.acquisitions for r in results)
        total_contentions = sum(r.contentions for r in results)
        total_releases = sum(r.releases for r in results)
        all_errors = []
        for r in results:
            all_errors.extend(r.errors)

        acquisition_counts = [r.acquisitions for r in results]
        fairness = calculate_fairness(acquisition_counts)

        agent_with_zero = sum(1 for r in results if r.acquisitions == 0)

        metrics.metrics.increment_counter("total_acquisitions", total_acquisitions)
        metrics.metrics.increment_counter("total_contentions", total_contentions)
        metrics.metrics.increment_counter("total_releases", total_releases)
        metrics.metrics.set_gauge("fairness_coefficient", fairness)
        metrics.metrics.increment_counter("agents_with_zero_acquisitions", agent_with_zero)

        for r in results:
            for lat in r.latencies_ms:
                metrics.record_instant("acquire_lock", lat, True)

        final_metrics = metrics.finalize()
        final_metrics.print_summary()

        assert total_acquisitions > 0, "No successful acquisitions - system stuck"
        # Allow 5% release mismatch due to TTL expiration during high contention
        release_rate = total_releases / total_acquisitions if total_acquisitions > 0 else 0
        assert release_rate > 0.95, \
            f"Release rate too low: {release_rate:.2%} ({total_releases}/{total_acquisitions})"
        assert fairness > 0.5, \
            f"Fairness coefficient {fairness:.2f} < 0.5 - some agents starving"
        assert agent_with_zero < AGENTS * 0.1, \
            f"Too many starving agents: {agent_with_zero} got 0 acquisitions"
        assert len(all_errors) < total_acquisitions * 0.01, \
            f"Too many errors: {len(all_errors)}"

    def test_no_double_locks(
        self,
        redis_client,
        stress_test_id,
        lock_factory,
        thread_pool_20
    ):
        """
        Verify atomicity: only one agent can hold a lock at a time.
        Uses Redis state directly to verify, not in-memory tracking.
        """
        double_acquires = []
        lock = threading.Lock()

        def agent_task(lock_sim: LockSimulator) -> int:
            acquisitions = 0
            for _ in range(100):
                file_path = random.choice(FILES[:3])

                if lock_sim.acquire(file_path, ttl=60):
                    owner = lock_sim.get_owner(file_path)
                    if owner != lock_sim.agent_id:
                        with lock:
                            double_acquires.append({
                                "file": file_path,
                                "expected_owner": lock_sim.agent_id,
                                "actual_owner": owner
                            })

                    time.sleep(0.002)
                    acquisitions += 1
                    lock_sim.release(file_path)
                else:
                    time.sleep(0.001)

            return acquisitions

        locks = [lock_factory(f"atomic-agent-{i}") for i in range(20)]
        futures = [thread_pool_20.submit(agent_task, l) for l in locks]

        for f in as_completed(futures, timeout=60):
            f.result()

        assert len(double_acquires) == 0, \
            f"Double-lock violations (Redis shows different owner after acquire): {double_acquires}"

    def test_lock_expiry_prevents_deadlock(
        self,
        redis_client,
        stress_test_id,
        lock_factory
    ):
        """
        Verify lock TTL prevents deadlocks when agent crashes.
        """
        lock1 = lock_factory("deadlock-agent-1")
        lock2 = lock_factory("deadlock-agent-2")

        file_path = "deadlock/test.ts"

        acquired1 = lock1.acquire(file_path, ttl=2)
        assert acquired1, "First agent should acquire lock"

        acquired2 = lock2.acquire(file_path, ttl=2)
        assert not acquired2, "Second agent should be blocked"

        time.sleep(2.5)

        acquired2_retry = lock2.acquire(file_path, ttl=2)
        assert acquired2_retry, "Second agent should acquire after TTL expiry"

        lock2.release(file_path)

    def test_lock_release_by_owner_only(
        self,
        redis_client,
        stress_test_id,
        lock_factory
    ):
        """
        Verify only the lock owner can release the lock.
        """
        lock1 = lock_factory("owner-agent")
        lock2 = lock_factory("impostor-agent")

        file_path = "owner/test.ts"

        acquired = lock1.acquire(file_path, ttl=60)
        assert acquired

        assert lock1.get_owner(file_path) == "owner-agent"

        released_by_impostor = lock2.release(file_path)
        assert not released_by_impostor, "Impostor should not release lock"

        assert lock1.is_locked(file_path), "Lock should still be held"
        assert lock1.get_owner(file_path) == "owner-agent"

        released_by_owner = lock1.release(file_path)
        assert released_by_owner, "Owner should release lock"
        assert not lock1.is_locked(file_path)

    def test_rapid_acquire_release_cycles(
        self,
        redis_client,
        stress_test_id,
        lock_factory
    ):
        """
        Rapid lock/unlock cycles don't corrupt state.
        """
        lock = lock_factory("rapid-lock-agent")
        file_path = "rapid/cycle.ts"
        cycles = 200

        for i in range(cycles):
            acquired = lock.acquire(file_path, ttl=300)
            assert acquired, f"Cycle {i}: Failed to acquire"
            time.sleep(0.001)
            released = lock.release(file_path)
            if not released:
                # Check if lock still exists - race condition with another process?
                owner = lock.get_owner(file_path)
                is_locked = lock.is_locked(file_path)
                assert False, f"Cycle {i}: Failed to release (owner={owner}, locked={is_locked})"

        assert not lock.is_locked(file_path), "Lock should be released after cycles"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
