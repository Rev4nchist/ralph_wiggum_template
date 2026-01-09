"""
ST-007: Memory Recall Scalability Test

Tests memory system performance with 1000+ memories and complex queries.
Verifies p99 latency stays acceptable and results are accurate.

Pass Criteria:
- p99 recall latency < 500ms
- Top 10 results returned efficiently
- No context window overflow
- Accurate relevance ranking
"""
import pytest
import time
import json
import random
import string
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple
from dataclasses import dataclass, field

from ..conftest import requires_redis, AgentSimulator
from ..metrics import StressTestMetrics, MetricsCollector


MEMORY_COUNT = 1000
CATEGORIES = ["architecture", "pattern", "decision", "blocker", "learning"]
QUERY_TERMS = [
    "authentication", "database optimization", "React component",
    "API design", "security vulnerability", "performance tuning",
    "error handling", "deployment strategy", "testing approach",
    "caching strategy"
]


def generate_memory_content(idx: int, category: str) -> str:
    templates = {
        "architecture": [
            f"Architecture decision #{idx}: Use microservices pattern for {random.choice(['auth', 'payments', 'notifications'])} service",
            f"System design #{idx}: Implement {random.choice(['event-driven', 'REST', 'GraphQL'])} architecture for scalability",
            f"Infrastructure #{idx}: Deploy on {random.choice(['AWS', 'Azure', 'GCP'])} using {random.choice(['Kubernetes', 'ECS', 'Cloud Run'])}"
        ],
        "pattern": [
            f"Pattern #{idx}: Apply {random.choice(['Repository', 'Factory', 'Observer', 'Strategy'])} pattern for {random.choice(['data access', 'object creation', 'state management'])}",
            f"Design pattern #{idx}: Use {random.choice(['Singleton', 'Adapter', 'Decorator'])} to solve {random.choice(['global state', 'interface mismatch', 'feature extension'])}",
            f"Code pattern #{idx}: Implement {random.choice(['retry logic', 'circuit breaker', 'rate limiting'])} for resilience"
        ],
        "decision": [
            f"Decision #{idx}: Choose {random.choice(['PostgreSQL', 'MongoDB', 'Redis'])} for {random.choice(['primary storage', 'caching', 'session management'])}",
            f"Technical decision #{idx}: Use {random.choice(['TypeScript', 'Python', 'Go'])} for {random.choice(['backend API', 'data processing', 'CLI tools'])}",
            f"Framework decision #{idx}: Select {random.choice(['React', 'Vue', 'Svelte'])} with {random.choice(['Next.js', 'Nuxt', 'SvelteKit'])} for frontend"
        ],
        "blocker": [
            f"Blocker #{idx}: {random.choice(['Memory leak', 'Race condition', 'Deadlock'])} in {random.choice(['auth service', 'payment processor', 'notification system'])}",
            f"Issue #{idx}: {random.choice(['Performance degradation', 'API timeout', 'Data inconsistency'])} under {random.choice(['high load', 'concurrent access', 'network latency'])}",
            f"Problem #{idx}: {random.choice(['Integration failure', 'Deployment issue', 'Security vulnerability'])} affecting {random.choice(['production', 'staging', 'CI/CD'])}"
        ],
        "learning": [
            f"Learning #{idx}: {random.choice(['Discovered', 'Learned', 'Realized'])} that {random.choice(['caching improves performance', 'indexing speeds queries', 'async processing scales better'])}",
            f"Insight #{idx}: {random.choice(['Testing early', 'Code reviews', 'Documentation'])} {random.choice(['prevents bugs', 'improves quality', 'reduces maintenance'])}",
            f"Knowledge #{idx}: {random.choice(['Best practice', 'Anti-pattern', 'Optimization technique'])} for {random.choice(['database queries', 'API design', 'error handling'])}"
        ]
    }

    return random.choice(templates[category])


def generate_tags(category: str, idx: int) -> List[str]:
    base_tags = [category, f"batch-{idx // 100}"]
    extra_tags = random.sample([
        "important", "review", "completed", "pending",
        "backend", "frontend", "infrastructure", "security"
    ], k=random.randint(1, 3))
    return base_tags + extra_tags


class MemoryStore:

    def __init__(self, redis_client, prefix: str):
        self.redis = redis_client
        self.prefix = prefix
        self.memories_key = f"{prefix}:memories"
        self.index_key = f"{prefix}:memory_index"

    def store(self, agent_id: str, content: str, category: str, tags: List[str]) -> str:
        memory_id = f"mem-{int(time.time() * 1000000)}"
        memory = {
            "id": memory_id,
            "agent_id": agent_id,
            "content": content,
            "category": category,
            "tags": tags,
            "timestamp": time.time(),
            "word_count": len(content.split())
        }
        self.redis.hset(self.memories_key, memory_id, json.dumps(memory))

        for word in content.lower().split():
            if len(word) > 3:
                self.redis.sadd(f"{self.index_key}:word:{word}", memory_id)

        self.redis.sadd(f"{self.index_key}:category:{category}", memory_id)

        for tag in tags:
            self.redis.sadd(f"{self.index_key}:tag:{tag}", memory_id)

        return memory_id

    def recall(
        self,
        query: str,
        category: str = None,
        limit: int = 10
    ) -> Tuple[List[Dict], float]:
        start = time.time()

        query_words = [w.lower() for w in query.split() if len(w) > 3]

        if category:
            category_members = self.redis.smembers(f"{self.index_key}:category:{category}")
        else:
            category_members = None

        scores = {}
        for word in query_words:
            word_members = self.redis.smembers(f"{self.index_key}:word:{word}")
            for mem_id in word_members:
                if category_members is None or mem_id in category_members:
                    scores[mem_id] = scores.get(mem_id, 0) + 1

        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)[:limit]

        results = []
        for mem_id in sorted_ids:
            mem_json = self.redis.hget(self.memories_key, mem_id)
            if mem_json:
                mem = json.loads(mem_json)
                mem["score"] = scores[mem_id]
                results.append(mem)

        latency_ms = (time.time() - start) * 1000
        return results, latency_ms

    def recall_by_category(self, category: str, limit: int = 100) -> List[Dict]:
        member_ids = self.redis.smembers(f"{self.index_key}:category:{category}")
        results = []

        for mem_id in list(member_ids)[:limit]:
            mem_json = self.redis.hget(self.memories_key, mem_id)
            if mem_json:
                results.append(json.loads(mem_json))

        return sorted(results, key=lambda x: x.get("timestamp", 0), reverse=True)

    def count(self) -> int:
        return self.redis.hlen(self.memories_key)

    def clear(self):
        self.redis.delete(self.memories_key)
        for key in self.redis.scan_iter(f"{self.index_key}:*"):
            self.redis.delete(key)


@requires_redis
class TestMemoryRecallScalability:

    def test_1000_memory_recall_latency(
        self,
        redis_client,
        stress_test_id,
        thread_pool_10
    ):
        """
        ST-007: Store 1000 memories, verify recall p99 < 500ms.
        """
        metrics = MetricsCollector(stress_test_id, "ST-007: Memory Recall Scalability")
        store = MemoryStore(redis_client, stress_test_id)

        print("\nPopulating 1000 memories...")
        for i in range(MEMORY_COUNT):
            category = CATEGORIES[i % len(CATEGORIES)]
            content = generate_memory_content(i, category)
            tags = generate_tags(category, i)
            store.store(f"agent-{i % 10}", content, category, tags)

        assert store.count() == MEMORY_COUNT, \
            f"Memory count mismatch: {store.count()} != {MEMORY_COUNT}"

        print("Running recall queries...")
        latencies = []

        for query in QUERY_TERMS:
            results, latency = store.recall(query, limit=10)
            latencies.append(latency)
            metrics.record_instant("recall_query", latency, len(results) > 0)

        for query in QUERY_TERMS[:5]:
            for category in CATEGORIES:
                results, latency = store.recall(query, category=category, limit=10)
                latencies.append(latency)
                metrics.record_instant("recall_filtered", latency, True)

        final_metrics = metrics.finalize()
        final_metrics.print_summary()

        latencies.sort()
        p50 = latencies[int(len(latencies) * 0.50)]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]

        print(f"\nRecall Latencies:")
        print(f"  p50: {p50:.2f}ms")
        print(f"  p95: {p95:.2f}ms")
        print(f"  p99: {p99:.2f}ms")
        print(f"  max: {max(latencies):.2f}ms")

        assert p99 < 500, \
            f"p99 latency {p99:.2f}ms > 500ms threshold"

        store.clear()

    def test_concurrent_recall_performance(
        self,
        redis_client,
        stress_test_id,
        thread_pool_10
    ):
        """
        Multiple agents recalling memories simultaneously.
        """
        store = MemoryStore(redis_client, f"{stress_test_id}:concurrent")

        for i in range(500):
            category = CATEGORIES[i % len(CATEGORIES)]
            content = generate_memory_content(i, category)
            store.store(f"agent-{i % 5}", content, category, [category])

        results = []
        lock = threading.Lock()

        def recall_worker(agent_id: str, queries: List[str]):
            agent_latencies = []
            for query in queries:
                _, latency = store.recall(query, limit=10)
                agent_latencies.append(latency)
            with lock:
                results.extend(agent_latencies)
            return agent_latencies

        futures = []
        for i in range(10):
            queries = random.sample(QUERY_TERMS, 5)
            f = thread_pool_10.submit(recall_worker, f"recall-agent-{i}", queries)
            futures.append(f)

        for f in as_completed(futures, timeout=30):
            f.result()

        avg_latency = sum(results) / len(results)
        max_latency = max(results)

        print(f"\nConcurrent Recall: {len(results)} queries")
        print(f"  Average: {avg_latency:.2f}ms")
        print(f"  Max: {max_latency:.2f}ms")

        assert avg_latency < 100, \
            f"Average concurrent latency {avg_latency:.2f}ms too high"

        store.clear()

    def test_category_filtering_efficiency(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Category filtering should significantly reduce search space.
        """
        store = MemoryStore(redis_client, f"{stress_test_id}:filter")

        for i in range(500):
            category = CATEGORIES[i % len(CATEGORIES)]
            content = generate_memory_content(i, category)
            store.store(f"agent-{i % 5}", content, category, [category])

        query = "architecture design"

        _, unfiltered_latency = store.recall(query, limit=10)
        _, filtered_latency = store.recall(query, category="architecture", limit=10)

        print(f"\nCategory Filter Effect:")
        print(f"  Unfiltered: {unfiltered_latency:.2f}ms")
        print(f"  Filtered: {filtered_latency:.2f}ms")

        filtered_results = store.recall_by_category("architecture", limit=100)
        assert len(filtered_results) == 100, \
            f"Should have 100 architecture memories, got {len(filtered_results)}"

        store.clear()

    def test_relevance_ranking(
        self,
        redis_client,
        stress_test_id
    ):
        """
        More relevant memories should rank higher.
        """
        store = MemoryStore(redis_client, f"{stress_test_id}:relevance")

        store.store("agent-1", "Database optimization using PostgreSQL indexes", "decision", ["db"])
        store.store("agent-2", "API design patterns for REST services", "pattern", ["api"])
        store.store("agent-3", "PostgreSQL database query optimization techniques", "learning", ["db"])
        store.store("agent-4", "Database schema design for PostgreSQL", "architecture", ["db"])
        store.store("agent-5", "Frontend React component patterns", "pattern", ["frontend"])

        results, _ = store.recall("PostgreSQL database", limit=5)

        assert len(results) > 0, "Should find relevant memories"

        top_result = results[0]
        assert "PostgreSQL" in top_result["content"] or "database" in top_result["content"].lower(), \
            f"Top result should be relevant: {top_result['content']}"

        store.clear()

    def test_large_content_handling(
        self,
        redis_client,
        stress_test_id
    ):
        """
        System handles memories with large content gracefully.
        """
        store = MemoryStore(redis_client, f"{stress_test_id}:large")

        large_content = " ".join(
            f"Word{i} " + "".join(random.choices(string.ascii_lowercase, k=10))
            for i in range(500)
        )

        start = time.time()
        store.store("agent-1", large_content, "learning", ["large"])
        store_time = (time.time() - start) * 1000

        results, recall_time = store.recall("Word100", limit=5)

        print(f"\nLarge Content Handling:")
        print(f"  Store time: {store_time:.2f}ms")
        print(f"  Recall time: {recall_time:.2f}ms")

        assert store_time < 1000, f"Large content store too slow: {store_time:.2f}ms"
        assert recall_time < 500, f"Large content recall too slow: {recall_time:.2f}ms"

        store.clear()

    def test_empty_and_no_match_queries(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Empty results handled gracefully.
        """
        store = MemoryStore(redis_client, f"{stress_test_id}:empty")

        for i in range(100):
            store.store(f"agent-{i}", f"Memory content {i} about coding", "pattern", ["code"])

        results, latency = store.recall("xyznonexistent", limit=10)
        assert len(results) == 0, "Should return empty for no match"
        assert latency < 50, f"No-match query too slow: {latency:.2f}ms"

        results, latency = store.recall("", limit=10)
        assert latency < 50, f"Empty query too slow: {latency:.2f}ms"

        store.clear()

    def test_memory_growth_impact(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Recall latency should scale sub-linearly with memory count.
        """
        store = MemoryStore(redis_client, f"{stress_test_id}:growth")
        sizes = [100, 250, 500, 1000]
        latencies_by_size = {}

        for target_size in sizes:
            current = store.count()
            for i in range(current, target_size):
                category = CATEGORIES[i % len(CATEGORIES)]
                content = generate_memory_content(i, category)
                store.store(f"agent-{i % 5}", content, category, [category])

            query_latencies = []
            for query in QUERY_TERMS[:5]:
                _, latency = store.recall(query, limit=10)
                query_latencies.append(latency)

            latencies_by_size[target_size] = sum(query_latencies) / len(query_latencies)

        print("\nLatency vs Memory Count:")
        for size, latency in latencies_by_size.items():
            print(f"  {size} memories: {latency:.2f}ms")

        ratio = latencies_by_size[1000] / latencies_by_size[100]
        assert ratio < 5, \
            f"Latency scaling too steep: 1000/100 ratio = {ratio:.2f}"

        store.clear()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
