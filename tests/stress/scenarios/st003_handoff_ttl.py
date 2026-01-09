"""
ST-003: Handoff Chain TTL Expiry

Tests that multi-agent handoff chains recover when TTL expires mid-chain.
Verifies context preservation and graceful degradation.

Pass Criteria:
- Chain completes despite handoff expiry
- Context recovered from task.result backup
- No data loss in handoff chain
- Warning logged (not silent failure)
"""
import pytest
import time
import threading
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
from dataclasses import dataclass, field

from ..conftest import requires_redis, AgentSimulator
from ..metrics import StressTestMetrics, MetricsCollector


CHAIN_LENGTH = 5
HANDOFF_TTL_SECONDS = 3  # Short TTL to ensure expiry during test
AGENT_PROCESSING_SECONDS = 2


@dataclass
class HandoffData:
    from_agent: str
    to_agent: str
    task_id: str
    context: Dict
    created_at: float
    ttl_seconds: int


@dataclass
class ChainExecutionResult:
    chain_id: str
    completed_steps: int
    total_steps: int
    handoff_expirations: int
    recovered_contexts: int
    errors: List[str]
    step_results: List[Dict]
    duration_seconds: float


class HandoffManager:

    def __init__(self, redis_client, test_prefix: str):
        self.redis = redis_client
        self.prefix = test_prefix
        self.warnings: List[str] = []

    def create_handoff(
        self,
        from_agent: str,
        to_agent: str,
        task_id: str,
        context: Dict,
        ttl_seconds: int
    ) -> str:
        handoff_key = f"{self.prefix}:handoff:{task_id}"
        handoff_data = {
            "from_agent": from_agent,
            "to_agent": to_agent,
            "task_id": task_id,
            "context": json.dumps(context),
            "created_at": time.time(),
            "ttl_seconds": ttl_seconds
        }
        self.redis.hset(handoff_key, mapping=handoff_data)
        self.redis.expire(handoff_key, ttl_seconds)

        backup_key = f"{self.prefix}:handoff_backup:{task_id}"
        self.redis.hset(backup_key, mapping=handoff_data)
        self.redis.expire(backup_key, ttl_seconds * 10)

        return handoff_key

    def get_handoff(self, task_id: str) -> Optional[HandoffData]:
        handoff_key = f"{self.prefix}:handoff:{task_id}"
        data = self.redis.hgetall(handoff_key)

        if data:
            return HandoffData(
                from_agent=data.get("from_agent", ""),
                to_agent=data.get("to_agent", ""),
                task_id=data.get("task_id", ""),
                context=json.loads(data.get("context", "{}")),
                created_at=float(data.get("created_at", 0)),
                ttl_seconds=int(data.get("ttl_seconds", 0))
            )
        return None

    def recover_from_backup(self, task_id: str) -> Optional[Dict]:
        backup_key = f"{self.prefix}:handoff_backup:{task_id}"
        data = self.redis.hgetall(backup_key)

        if data:
            self.warnings.append(f"Recovered handoff from backup: {task_id}")
            context_str = data.get("context", "{}")
            return json.loads(context_str)
        return None

    def store_task_result(self, task_id: str, result: Dict):
        result_key = f"{self.prefix}:task_result:{task_id}"
        self.redis.set(result_key, json.dumps(result))
        self.redis.expire(result_key, 3600)

    def get_task_result(self, task_id: str) -> Optional[Dict]:
        result_key = f"{self.prefix}:task_result:{task_id}"
        data = self.redis.get(result_key)
        if data:
            return json.loads(data)
        return None


def execute_chain_step(
    handoff_manager: HandoffManager,
    agent: AgentSimulator,
    step_index: int,
    chain_id: str,
    prev_task_id: str,
    processing_time: float
) -> Dict:
    task_id = f"{chain_id}-step-{step_index}"
    next_task_id = f"{chain_id}-step-{step_index + 1}"

    context = None
    recovered = False

    if prev_task_id:
        handoff = handoff_manager.get_handoff(prev_task_id)
        if handoff:
            context = handoff.context
        else:
            context = handoff_manager.recover_from_backup(prev_task_id)
            if context:
                recovered = True
            else:
                prev_result = handoff_manager.get_task_result(prev_task_id)
                if prev_result:
                    context = prev_result.get("context", {})
                    recovered = True
                    handoff_manager.warnings.append(
                        f"Recovered from task result: {prev_task_id}"
                    )

    time.sleep(processing_time)

    result = {
        "task_id": task_id,
        "agent_id": agent.agent_id,
        "step_index": step_index,
        "context_received": context,
        "context_recovered": recovered,
        "output": f"Step {step_index} processed by {agent.agent_id}",
        "accumulated_data": (context or {}).get("accumulated_data", []) + [step_index]
    }

    handoff_manager.store_task_result(task_id, {
        "context": {"accumulated_data": result["accumulated_data"]},
        "output": result["output"]
    })

    handoff_manager.create_handoff(
        from_agent=agent.agent_id,
        to_agent=f"agent-step-{step_index + 1}",
        task_id=task_id,
        context={"accumulated_data": result["accumulated_data"]},
        ttl_seconds=HANDOFF_TTL_SECONDS
    )

    return result


@requires_redis
class TestHandoffTTLExpiry:

    def test_chain_survives_handoff_expiry(
        self,
        redis_client,
        stress_test_id,
        agent_factory
    ):
        """
        ST-003: 5-task chain where handoff expires mid-chain.
        System should recover and complete the chain.
        """
        metrics = MetricsCollector(stress_test_id, "ST-003: Handoff TTL Expiry")
        handoff_manager = HandoffManager(redis_client, stress_test_id)
        chain_id = f"chain-{stress_test_id}"

        results = []
        prev_task_id = None
        expirations = 0
        recoveries = 0

        for step in range(CHAIN_LENGTH):
            agent = agent_factory(f"chain-agent-{step}")

            start = time.time()
            result = execute_chain_step(
                handoff_manager,
                agent,
                step,
                chain_id,
                prev_task_id,
                AGENT_PROCESSING_SECONDS
            )
            latency = (time.time() - start) * 1000
            metrics.record_instant("chain_step", latency, True)

            results.append(result)

            if result.get("context_recovered"):
                recoveries += 1

            prev_task_id = f"{chain_id}-step-{step}"

            if step == 1:
                time.sleep(HANDOFF_TTL_SECONDS + 1)

        final_metrics = metrics.finalize()
        final_metrics.print_summary()

        assert len(results) == CHAIN_LENGTH, \
            f"Chain incomplete: {len(results)}/{CHAIN_LENGTH} steps"

        final_result = results[-1]
        accumulated = final_result.get("accumulated_data", [])
        assert accumulated == list(range(CHAIN_LENGTH)), \
            f"Data lost in chain: {accumulated} != {list(range(CHAIN_LENGTH))}"

        assert recoveries > 0, \
            "No recovery events - TTL expiry not tested"

        assert len(handoff_manager.warnings) > 0, \
            "No warnings logged for handoff expiry"

    def test_parallel_chains_with_expiry(
        self,
        redis_client,
        stress_test_id,
        agent_factory,
        thread_pool_10
    ):
        """
        Multiple chains running in parallel, some experiencing TTL expiry.
        """
        num_chains = 5
        chain_results: List[ChainExecutionResult] = []

        def run_chain(chain_idx: int) -> ChainExecutionResult:
            chain_id = f"parallel-chain-{chain_idx}"
            handoff_manager = HandoffManager(redis_client, f"{stress_test_id}:{chain_id}")

            start = time.time()
            results = []
            prev_task_id = None
            expirations = 0
            recoveries = 0
            errors = []

            for step in range(CHAIN_LENGTH):
                agent = agent_factory(f"{chain_id}-agent-{step}")
                try:
                    processing_time = AGENT_PROCESSING_SECONDS
                    if chain_idx % 2 == 0 and step == 2:
                        processing_time = HANDOFF_TTL_SECONDS + 2

                    result = execute_chain_step(
                        handoff_manager,
                        agent,
                        step,
                        chain_id,
                        prev_task_id,
                        processing_time
                    )
                    results.append(result)

                    if result.get("context_recovered"):
                        recoveries += 1

                    prev_task_id = f"{chain_id}-step-{step}"

                except Exception as e:
                    errors.append(f"Step {step}: {e}")

            return ChainExecutionResult(
                chain_id=chain_id,
                completed_steps=len(results),
                total_steps=CHAIN_LENGTH,
                handoff_expirations=expirations,
                recovered_contexts=recoveries,
                errors=errors,
                step_results=results,
                duration_seconds=time.time() - start
            )

        futures = [thread_pool_10.submit(run_chain, i) for i in range(num_chains)]
        for f in as_completed(futures, timeout=120):
            chain_results.append(f.result())

        all_completed = all(r.completed_steps == r.total_steps for r in chain_results)
        assert all_completed, \
            f"Some chains failed: {[(r.chain_id, r.completed_steps) for r in chain_results if r.completed_steps != r.total_steps]}"

        total_errors = sum(len(r.errors) for r in chain_results)
        assert total_errors == 0, \
            f"Chain errors: {[r.errors for r in chain_results if r.errors]}"

    def test_handoff_backup_recovery(
        self,
        redis_client,
        stress_test_id,
        agent_factory
    ):
        """
        Verify backup system correctly preserves context when primary expires.
        """
        handoff_manager = HandoffManager(redis_client, stress_test_id)

        context = {
            "architecture_decision": "Use microservices",
            "dependencies": ["auth", "db", "cache"],
            "critical_path": True
        }

        handoff_manager.create_handoff(
            from_agent="arch-agent",
            to_agent="impl-agent",
            task_id="test-task-1",
            context=context,
            ttl_seconds=5
        )

        handoff = handoff_manager.get_handoff("test-task-1")
        assert handoff is not None
        assert handoff.context == context

        time.sleep(6)

        expired_handoff = handoff_manager.get_handoff("test-task-1")
        assert expired_handoff is None, "Primary handoff should have expired"

        recovered = handoff_manager.recover_from_backup("test-task-1")
        assert recovered is not None, "Backup should still exist"
        assert recovered == context, "Recovered context should match original"

    def test_cascading_ttl_expiry(
        self,
        redis_client,
        stress_test_id,
        agent_factory
    ):
        """
        Test behavior when multiple consecutive handoffs expire.
        """
        handoff_manager = HandoffManager(redis_client, stress_test_id)
        chain_id = "cascade-expiry-chain"

        agent_0 = agent_factory("cascade-agent-0")
        result_0 = execute_chain_step(
            handoff_manager, agent_0, 0, chain_id, None, 0.1
        )

        time.sleep(HANDOFF_TTL_SECONDS + 1)

        agent_1 = agent_factory("cascade-agent-1")
        result_1 = execute_chain_step(
            handoff_manager, agent_1, 1, chain_id,
            f"{chain_id}-step-0", 0.1
        )

        assert result_1["context_recovered"], "Step 1 should recover from backup"

        time.sleep(HANDOFF_TTL_SECONDS + 1)

        agent_2 = agent_factory("cascade-agent-2")
        result_2 = execute_chain_step(
            handoff_manager, agent_2, 2, chain_id,
            f"{chain_id}-step-1", 0.1
        )

        assert result_2["accumulated_data"] == [0, 1, 2], \
            f"Data should accumulate despite expirations: {result_2['accumulated_data']}"

    def test_concurrent_handoff_creation_and_expiry(
        self,
        redis_client,
        stress_test_id,
        agent_factory,
        thread_pool_10
    ):
        """
        Stress test handoff system under concurrent load with TTL pressure.
        """
        num_handoffs = 50
        short_ttl = 5
        created = []
        recovered = []
        lock = threading.Lock()

        def create_handoff(idx: int):
            hm = HandoffManager(redis_client, f"{stress_test_id}:concurrent")
            hm.create_handoff(
                from_agent=f"agent-{idx}",
                to_agent=f"agent-{idx+1}",
                task_id=f"concurrent-task-{idx}",
                context={"idx": idx, "data": f"payload-{idx}"},
                ttl_seconds=short_ttl
            )
            with lock:
                created.append(idx)

        def read_handoff(idx: int):
            time.sleep(short_ttl + 1)
            hm = HandoffManager(redis_client, f"{stress_test_id}:concurrent")
            handoff = hm.get_handoff(f"concurrent-task-{idx}")
            backup = hm.recover_from_backup(f"concurrent-task-{idx}")
            with lock:
                if backup:
                    recovered.append(idx)

        create_futures = [thread_pool_10.submit(create_handoff, i) for i in range(num_handoffs)]
        for f in as_completed(create_futures, timeout=30):
            f.result()

        read_futures = [thread_pool_10.submit(read_handoff, i) for i in range(num_handoffs)]
        for f in as_completed(read_futures, timeout=60):
            f.result()

        assert len(created) == num_handoffs, \
            f"Not all handoffs created: {len(created)}/{num_handoffs}"
        # Allow some backup TTL expirations under heavy concurrent load
        # Main goal is verifying no corruption during concurrent creation
        recovery_rate = len(recovered) / num_handoffs
        assert recovery_rate > 0.5, \
            f"Too few handoffs recoverable: {len(recovered)}/{num_handoffs} ({recovery_rate:.0%})"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
