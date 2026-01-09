"""
ST-010: Memory Conflict Resolution Test

Tests behavior when multiple agents store conflicting decisions
simultaneously. Verifies no silent overwrites and conflict visibility.

Pass Criteria:
- All conflicting stores preserved (no silent overwrite)
- Recall returns all conflicts (user sees choices)
- No data loss
- Timestamps preserved for ordering
"""
import pytest
import time
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Set
from dataclasses import dataclass, field

from ..conftest import requires_redis
from ..metrics import MetricsCollector


@dataclass
class ConflictingDecision:
    agent_id: str
    topic: str
    choice: str
    rationale: str
    timestamp: float = field(default_factory=time.time)


class ConflictAwareMemoryStore:

    def __init__(self, redis_client, prefix: str):
        self.redis = redis_client
        self.prefix = prefix
        self.memories_key = f"{prefix}:memories"
        self.topics_key = f"{prefix}:topics"
        self.conflicts_key = f"{prefix}:conflicts"

    def store_decision(self, decision: ConflictingDecision) -> str:
        memory_id = f"dec-{int(time.time() * 1000000)}-{decision.agent_id[:8]}"

        memory = {
            "id": memory_id,
            "agent_id": decision.agent_id,
            "topic": decision.topic,
            "choice": decision.choice,
            "rationale": decision.rationale,
            "timestamp": decision.timestamp,
            "category": "decision"
        }

        self.redis.hset(self.memories_key, memory_id, json.dumps(memory))
        self.redis.sadd(f"{self.topics_key}:{decision.topic}", memory_id)

        self._detect_conflict(decision.topic, memory_id)

        return memory_id

    def _detect_conflict(self, topic: str, new_memory_id: str):
        topic_memories = self.redis.smembers(f"{self.topics_key}:{topic}")

        if len(topic_memories) <= 1:
            return

        choices = {}
        for mem_id in topic_memories:
            mem_json = self.redis.hget(self.memories_key, mem_id)
            if mem_json:
                mem = json.loads(mem_json)
                choice = mem.get("choice")
                if choice not in choices:
                    choices[choice] = []
                choices[choice].append(mem_id)

        if len(choices) > 1:
            conflict_entry = {
                "topic": topic,
                "choices": {k: list(v) for k, v in choices.items()},
                "detected_at": time.time(),
                "triggered_by": new_memory_id
            }
            self.redis.lpush(self.conflicts_key, json.dumps(conflict_entry))

    def get_decisions_for_topic(self, topic: str) -> List[Dict]:
        topic_memories = self.redis.smembers(f"{self.topics_key}:{topic}")
        results = []

        for mem_id in topic_memories:
            mem_json = self.redis.hget(self.memories_key, mem_id)
            if mem_json:
                results.append(json.loads(mem_json))

        return sorted(results, key=lambda x: x.get("timestamp", 0), reverse=True)

    def get_conflicts(self) -> List[Dict]:
        conflicts = self.redis.lrange(self.conflicts_key, 0, -1)
        return [json.loads(c) for c in conflicts]

    def count_memories(self) -> int:
        return self.redis.hlen(self.memories_key)

    def get_unique_choices(self, topic: str) -> Set[str]:
        decisions = self.get_decisions_for_topic(topic)
        return {d.get("choice") for d in decisions if d.get("choice")}


@requires_redis
class TestMemoryConflict:

    def test_conflicting_decisions_all_stored(
        self,
        redis_client,
        stress_test_id,
        thread_pool_10
    ):
        """
        ST-010: 5 agents store conflicting database decisions simultaneously.
        All 5 should be preserved.
        """
        store = ConflictAwareMemoryStore(redis_client, stress_test_id)

        topic = "database_choice"
        decisions = [
            ConflictingDecision(
                agent_id=f"agent-{i}",
                topic=topic,
                choice=["PostgreSQL", "MySQL", "MongoDB", "SQLite", "Redis"][i],
                rationale=f"Agent {i} prefers this for {['reliability', 'performance', 'flexibility', 'simplicity', 'speed'][i]}"
            )
            for i in range(5)
        ]

        stored_ids = []
        lock = threading.Lock()

        def store_decision(decision: ConflictingDecision):
            mem_id = store.store_decision(decision)
            with lock:
                stored_ids.append(mem_id)
            return mem_id

        futures = [
            thread_pool_10.submit(store_decision, d)
            for d in decisions
        ]

        for f in as_completed(futures, timeout=10):
            f.result()

        assert len(stored_ids) == 5, \
            f"All 5 decisions should be stored: {len(stored_ids)}"

        retrieved = store.get_decisions_for_topic(topic)
        assert len(retrieved) == 5, \
            f"All 5 decisions should be retrievable: {len(retrieved)}"

        unique_choices = store.get_unique_choices(topic)
        assert len(unique_choices) == 5, \
            f"All 5 unique choices should be visible: {unique_choices}"

    def test_conflict_detection(
        self,
        redis_client,
        stress_test_id
    ):
        """
        System should detect and log conflicts.
        """
        store = ConflictAwareMemoryStore(redis_client, f"{stress_test_id}:detect")

        store.store_decision(ConflictingDecision(
            agent_id="agent-1",
            topic="auth_method",
            choice="JWT",
            rationale="Stateless"
        ))

        store.store_decision(ConflictingDecision(
            agent_id="agent-2",
            topic="auth_method",
            choice="Session",
            rationale="More secure"
        ))

        conflicts = store.get_conflicts()
        assert len(conflicts) > 0, "Should detect conflict"

        conflict = conflicts[0]
        assert conflict["topic"] == "auth_method"
        assert "JWT" in conflict["choices"]
        assert "Session" in conflict["choices"]

    def test_no_silent_overwrite(
        self,
        redis_client,
        stress_test_id,
        thread_pool_10
    ):
        """
        Concurrent writes should not silently overwrite each other.
        """
        store = ConflictAwareMemoryStore(redis_client, f"{stress_test_id}:overwrite")

        topic = "api_style"
        num_agents = 20

        def rapid_store(agent_id: str):
            for i in range(5):
                store.store_decision(ConflictingDecision(
                    agent_id=agent_id,
                    topic=topic,
                    choice=f"Style-{agent_id}-{i}",
                    rationale=f"Iteration {i}"
                ))
            return agent_id

        futures = [
            thread_pool_10.submit(rapid_store, f"rapid-agent-{i}")
            for i in range(num_agents)
        ]

        for f in as_completed(futures, timeout=30):
            f.result()

        total_memories = store.count_memories()
        expected = num_agents * 5

        assert total_memories == expected, \
            f"No overwrites: expected {expected}, got {total_memories}"

    def test_timestamp_ordering_preserved(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Timestamps should allow ordering of conflicting decisions.
        """
        store = ConflictAwareMemoryStore(redis_client, f"{stress_test_id}:timestamp")

        topic = "framework_choice"

        for i, choice in enumerate(["React", "Vue", "Svelte"]):
            store.store_decision(ConflictingDecision(
                agent_id=f"agent-{i}",
                topic=topic,
                choice=choice,
                rationale=f"Prefer {choice}"
            ))
            time.sleep(0.01)

        decisions = store.get_decisions_for_topic(topic)

        timestamps = [d["timestamp"] for d in decisions]
        assert timestamps == sorted(timestamps, reverse=True), \
            "Decisions should be ordered by timestamp (newest first)"

    def test_conflict_with_same_choice_different_rationale(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Same choice with different rationale is still conflict-free
        but all rationales should be preserved.
        """
        store = ConflictAwareMemoryStore(redis_client, f"{stress_test_id}:rationale")

        topic = "db_choice_unanimous"

        for i in range(5):
            store.store_decision(ConflictingDecision(
                agent_id=f"agent-{i}",
                topic=topic,
                choice="PostgreSQL",
                rationale=f"Reason {i}: {['ACID', 'JSON support', 'Extensions', 'Performance', 'Community'][i]}"
            ))

        decisions = store.get_decisions_for_topic(topic)

        assert len(decisions) == 5, "All 5 should be stored"

        unique_choices = store.get_unique_choices(topic)
        assert len(unique_choices) == 1, "All chose PostgreSQL"

        rationales = {d["rationale"] for d in decisions}
        assert len(rationales) == 5, "All rationales preserved"

    def test_multiple_topics_isolated(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Conflicts in different topics should be isolated.
        """
        store = ConflictAwareMemoryStore(redis_client, f"{stress_test_id}:isolated")

        store.store_decision(ConflictingDecision(
            agent_id="agent-1", topic="database", choice="PostgreSQL", rationale="R1"
        ))
        store.store_decision(ConflictingDecision(
            agent_id="agent-2", topic="database", choice="MySQL", rationale="R2"
        ))

        store.store_decision(ConflictingDecision(
            agent_id="agent-1", topic="cache", choice="Redis", rationale="R3"
        ))
        store.store_decision(ConflictingDecision(
            agent_id="agent-2", topic="cache", choice="Memcached", rationale="R4"
        ))

        db_decisions = store.get_decisions_for_topic("database")
        cache_decisions = store.get_decisions_for_topic("cache")

        assert len(db_decisions) == 2, "2 database decisions"
        assert len(cache_decisions) == 2, "2 cache decisions"

        db_choices = {d["choice"] for d in db_decisions}
        cache_choices = {d["choice"] for d in cache_decisions}

        assert db_choices == {"PostgreSQL", "MySQL"}
        assert cache_choices == {"Redis", "Memcached"}

    def test_high_contention_conflict_scenario(
        self,
        redis_client,
        stress_test_id,
        thread_pool_20
    ):
        """
        High contention: 50 agents making decisions on 5 topics.
        """
        store = ConflictAwareMemoryStore(redis_client, f"{stress_test_id}:contention")

        topics = ["database", "cache", "queue", "search", "monitoring"]
        choices_per_topic = {
            "database": ["PostgreSQL", "MySQL", "MongoDB"],
            "cache": ["Redis", "Memcached", "Hazelcast"],
            "queue": ["RabbitMQ", "Kafka", "SQS"],
            "search": ["Elasticsearch", "Solr", "Meilisearch"],
            "monitoring": ["Prometheus", "Datadog", "NewRelic"]
        }

        import random

        def agent_makes_decisions(agent_id: str):
            for topic in topics:
                choice = random.choice(choices_per_topic[topic])
                store.store_decision(ConflictingDecision(
                    agent_id=agent_id,
                    topic=topic,
                    choice=choice,
                    rationale=f"{agent_id} chose {choice}"
                ))
            return agent_id

        futures = [
            thread_pool_20.submit(agent_makes_decisions, f"agent-{i}")
            for i in range(50)
        ]

        for f in as_completed(futures, timeout=60):
            f.result()

        total = store.count_memories()
        expected = 50 * 5

        assert total == expected, \
            f"All decisions stored: {total} vs {expected}"

        for topic in topics:
            decisions = store.get_decisions_for_topic(topic)
            assert len(decisions) == 50, \
                f"Topic {topic}: expected 50, got {len(decisions)}"

        conflicts = store.get_conflicts()
        assert len(conflicts) > 0, "Should have detected conflicts"
        print(f"\nDetected {len(conflicts)} conflict events across {len(topics)} topics")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
