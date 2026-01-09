"""
ST-001: Memory Coherence Under Load

Tests that Redis memory operations remain consistent when 10+ agents
write simultaneously. Verifies no lost writes, duplicates, or corruption.

Pass Criteria:
- 100% memory persistence (1000 memories from 10 agents)
- 0 duplicate IDs
- 0 corrupted content
- p99 write latency < 100ms
"""
import pytest
import json
import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Set
from dataclasses import dataclass, field

from ..conftest import requires_redis, AgentSimulator
from ..metrics import StressTestMetrics, MetricsCollector, assert_metrics_pass


AGENTS = 10
MEMORIES_PER_AGENT = 100
TOTAL_EXPECTED = AGENTS * MEMORIES_PER_AGENT
CATEGORIES = ["architecture", "pattern", "decision", "blocker", "learning"]


@dataclass
class MemoryCoherenceResult:
    agent_id: str
    memories_stored: List[str]
    latencies_ms: List[float]
    errors: List[str]
    duration_seconds: float


def agent_memory_task(
    agent: AgentSimulator,
    memories_count: int,
    categories: List[str]
) -> MemoryCoherenceResult:
    start = time.time()
    memories_stored = []
    latencies = []
    errors = []

    for i in range(memories_count):
        category = categories[i % len(categories)]
        content = f"Memory from {agent.agent_id}: item {i} - {uuid.uuid4().hex[:8]}"
        tags = [f"tag-{agent.agent_id}", f"batch-{i//10}"]

        op_start = time.time()
        try:
            mem_id = agent.store_memory(content, category, tags)
            latency = (time.time() - op_start) * 1000
            latencies.append(latency)

            if mem_id:
                memories_stored.append(mem_id)
            else:
                errors.append(f"Failed to store memory {i}")
        except Exception as e:
            errors.append(f"Exception storing memory {i}: {e}")
            latencies.append((time.time() - op_start) * 1000)

    return MemoryCoherenceResult(
        agent_id=agent.agent_id,
        memories_stored=memories_stored,
        latencies_ms=latencies,
        errors=errors,
        duration_seconds=time.time() - start
    )


@requires_redis
class TestMemoryCoherence:

    def test_concurrent_memory_writes(
        self,
        redis_client,
        stress_test_id,
        agent_factory,
        thread_pool_10
    ):
        """
        ST-001: 10 agents write 100 memories each simultaneously.
        Verify all 1000 memories persist without duplicates or corruption.
        """
        metrics = MetricsCollector(stress_test_id, "ST-001: Memory Coherence")

        agents = [agent_factory(f"mem-agent-{i}") for i in range(AGENTS)]

        def run_agent(agent: AgentSimulator) -> MemoryCoherenceResult:
            return agent_memory_task(agent, MEMORIES_PER_AGENT, CATEGORIES)

        futures = {thread_pool_10.submit(run_agent, agent): agent for agent in agents}
        results: List[MemoryCoherenceResult] = []

        for future in as_completed(futures, timeout=60):
            result = future.result()
            results.append(result)
            for latency in result.latencies_ms:
                metrics.record_instant("store_memory", latency, latency > 0)

        all_memory_ids: List[str] = []
        all_errors: List[str] = []
        for r in results:
            all_memory_ids.extend(r.memories_stored)
            all_errors.extend(r.errors)

        memories_key = f"{stress_test_id}:memories"
        stored_memories = redis_client.hgetall(memories_key)

        unique_ids = set(all_memory_ids)
        duplicate_count = len(all_memory_ids) - len(unique_ids)

        corrupted = 0
        for mem_id, mem_json in stored_memories.items():
            try:
                data = json.loads(mem_json)
                assert "content" in data
                assert "category" in data
                assert "agent_id" in data
            except (json.JSONDecodeError, AssertionError):
                corrupted += 1

        metrics.metrics.increment_counter("total_memories", len(stored_memories))
        metrics.metrics.increment_counter("duplicates", duplicate_count)
        metrics.metrics.increment_counter("corrupted", corrupted)
        metrics.metrics.set_gauge("success_rate", len(stored_memories) / TOTAL_EXPECTED)

        final_metrics = metrics.finalize()
        final_metrics.print_summary()

        assert len(stored_memories) == TOTAL_EXPECTED, \
            f"Lost writes: expected {TOTAL_EXPECTED}, got {len(stored_memories)}"
        assert duplicate_count == 0, \
            f"Duplicate IDs detected: {duplicate_count}"
        assert corrupted == 0, \
            f"Corrupted memories: {corrupted}"
        assert final_metrics.latency_p99_ms < 100, \
            f"p99 latency {final_metrics.latency_p99_ms}ms > 100ms threshold"
        assert len(all_errors) == 0, \
            f"Errors during test: {all_errors}"

    def test_memory_recall_after_concurrent_writes(
        self,
        redis_client,
        stress_test_id,
        agent_factory,
        thread_pool_10
    ):
        """
        After concurrent writes, verify recall returns correct results.
        """
        agents = [agent_factory(f"recall-agent-{i}") for i in range(5)]

        def run_agent(agent: AgentSimulator) -> MemoryCoherenceResult:
            return agent_memory_task(agent, 50, CATEGORIES)

        futures = [thread_pool_10.submit(run_agent, agent) for agent in agents]
        for f in as_completed(futures, timeout=30):
            f.result()

        reader = agent_factory("reader-agent")

        arch_results = reader.recall_memory("Memory architecture", "architecture")
        assert len(arch_results) > 0, "Should recall architecture memories"

        pattern_results = reader.recall_memory("Memory pattern", "pattern")
        assert len(pattern_results) > 0, "Should recall pattern memories"

        all_results = reader.recall_memory("Memory from")
        assert len(all_results) > 0, "Should recall memories without category filter"

    def test_category_distribution(
        self,
        redis_client,
        stress_test_id,
        agent_factory,
        thread_pool_10
    ):
        """
        Verify memories are distributed across categories correctly.
        """
        agents = [agent_factory(f"cat-agent-{i}") for i in range(AGENTS)]

        def run_agent(agent: AgentSimulator) -> MemoryCoherenceResult:
            return agent_memory_task(agent, MEMORIES_PER_AGENT, CATEGORIES)

        futures = [thread_pool_10.submit(run_agent, agent) for agent in agents]
        for f in as_completed(futures, timeout=60):
            f.result()

        memories_key = f"{stress_test_id}:memories"
        stored_memories = redis_client.hgetall(memories_key)

        category_counts = {cat: 0 for cat in CATEGORIES}
        for mem_json in stored_memories.values():
            mem = json.loads(mem_json)
            cat = mem.get("category")
            if cat in category_counts:
                category_counts[cat] += 1

        expected_per_cat = TOTAL_EXPECTED // len(CATEGORIES)
        for cat, count in category_counts.items():
            assert count == expected_per_cat, \
                f"Category {cat}: expected {expected_per_cat}, got {count}"

    def test_agent_isolation(
        self,
        redis_client,
        stress_test_id,
        agent_factory,
        thread_pool_10
    ):
        """
        Verify each agent's memories are tagged with correct agent_id.
        """
        agents = [agent_factory(f"iso-agent-{i}") for i in range(5)]

        def run_agent(agent: AgentSimulator) -> MemoryCoherenceResult:
            return agent_memory_task(agent, 20, CATEGORIES)

        futures = [thread_pool_10.submit(run_agent, agent) for agent in agents]
        for f in as_completed(futures, timeout=30):
            f.result()

        memories_key = f"{stress_test_id}:memories"
        stored_memories = redis_client.hgetall(memories_key)

        agent_memory_counts = {f"iso-agent-{i}": 0 for i in range(5)}
        for mem_json in stored_memories.values():
            mem = json.loads(mem_json)
            aid = mem.get("agent_id")
            if aid in agent_memory_counts:
                agent_memory_counts[aid] += 1

        for aid, count in agent_memory_counts.items():
            assert count == 20, \
                f"Agent {aid}: expected 20 memories, got {count}"

    def test_high_frequency_writes(
        self,
        redis_client,
        stress_test_id,
        agent_factory
    ):
        """
        Single agent writes 500 memories rapidly - stress single connection.
        """
        agent = agent_factory("rapid-agent")
        metrics = MetricsCollector(stress_test_id, "High Frequency Writes")

        for i in range(500):
            content = f"Rapid memory {i} - {uuid.uuid4().hex}"
            start = time.time()
            mem_id = agent.store_memory(content, "pattern", ["rapid"])
            latency = (time.time() - start) * 1000
            metrics.record_instant("store_memory", latency, bool(mem_id))

        final_metrics = metrics.finalize()

        assert len(agent.memories_stored) == 500
        assert final_metrics.success_rate >= 0.99, \
            f"Success rate {final_metrics.success_rate} < 99%"
        assert final_metrics.latency_p99_ms < 200, \
            f"p99 latency {final_metrics.latency_p99_ms}ms > 200ms"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
