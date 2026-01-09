"""
Stress Test Fixtures - Real Redis & Thread Pools

Provides:
- Real Redis connection (not fakeredis) for accurate concurrency testing
- Thread pool executor for parallel agent simulation
- Cleanup fixtures to isolate tests
- Metrics collection utilities
"""
import pytest
import redis
import time
import uuid
import json
import threading
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from typing import Generator, Dict, Any, List
from dataclasses import dataclass, field
import os

STRESS_TEST_PREFIX = "stress_test"
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_DB = int(os.environ.get("STRESS_TEST_DB", "2"))


def redis_available() -> bool:
    try:
        client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, socket_timeout=2)
        client.ping()
        return True
    except (redis.ConnectionError, redis.TimeoutError):
        return False


REDIS_AVAILABLE = redis_available()
requires_redis = pytest.mark.skipif(not REDIS_AVAILABLE, reason="Real Redis not available")


@pytest.fixture(scope="session")
def redis_client() -> Generator[redis.Redis, None, None]:
    if not REDIS_AVAILABLE:
        pytest.skip("Real Redis not available")
    client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
        socket_timeout=30
    )
    yield client
    client.close()


@pytest.fixture
def clean_redis(redis_client: redis.Redis) -> Generator[redis.Redis, None, None]:
    test_id = f"{STRESS_TEST_PREFIX}:{uuid.uuid4().hex[:8]}"
    yield redis_client
    for key in redis_client.scan_iter(f"{test_id}:*"):
        redis_client.delete(key)


@pytest.fixture
def stress_test_id() -> str:
    return f"{STRESS_TEST_PREFIX}:{uuid.uuid4().hex[:8]}"


@pytest.fixture
def thread_pool_10() -> Generator[ThreadPoolExecutor, None, None]:
    pool = ThreadPoolExecutor(max_workers=10)
    yield pool
    pool.shutdown(wait=True)


@pytest.fixture
def thread_pool_100() -> Generator[ThreadPoolExecutor, None, None]:
    pool = ThreadPoolExecutor(max_workers=100)
    yield pool
    pool.shutdown(wait=True)


@pytest.fixture
def thread_pool_20() -> Generator[ThreadPoolExecutor, None, None]:
    pool = ThreadPoolExecutor(max_workers=20)
    yield pool
    pool.shutdown(wait=True)


@dataclass
class AgentSimulator:
    agent_id: str
    redis_client: redis.Redis
    test_prefix: str
    memories_stored: List[str] = field(default_factory=list)
    operations: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def store_memory(self, content: str, category: str = "general", tags: List[str] = None) -> str:
        memory_id = f"mem-{uuid.uuid4().hex[:8]}"
        key = f"{self.test_prefix}:memories"
        memory = {
            "id": memory_id,
            "content": content,
            "category": category,
            "tags": tags or [],
            "agent_id": self.agent_id,
            "created_at": time.time()
        }
        start = time.time()
        try:
            self.redis_client.hset(key, memory_id, json.dumps(memory))
            self.memories_stored.append(memory_id)
            self.operations.append({
                "type": "store_memory",
                "memory_id": memory_id,
                "latency_ms": (time.time() - start) * 1000,
                "success": True
            })
            return memory_id
        except Exception as e:
            self.errors.append(f"store_memory failed: {e}")
            self.operations.append({
                "type": "store_memory",
                "memory_id": memory_id,
                "latency_ms": (time.time() - start) * 1000,
                "success": False,
                "error": str(e)
            })
            return ""

    def recall_memory(self, query: str, category: str = None) -> List[Dict]:
        key = f"{self.test_prefix}:memories"
        start = time.time()
        try:
            all_memories = self.redis_client.hgetall(key)
            results = []
            query_words = set(query.lower().split())
            for mem_id, mem_json in all_memories.items():
                mem = json.loads(mem_json)
                content_words = set(mem["content"].lower().split())
                score = len(query_words & content_words)
                if category and mem.get("category") != category:
                    continue
                if score > 0:
                    results.append({"memory": mem, "score": score})
            results.sort(key=lambda x: x["score"], reverse=True)
            self.operations.append({
                "type": "recall_memory",
                "query": query,
                "results_count": len(results),
                "latency_ms": (time.time() - start) * 1000,
                "success": True
            })
            return results[:10]
        except Exception as e:
            self.errors.append(f"recall_memory failed: {e}")
            return []

    def create_handoff(self, task_id: str, summary: str, next_steps: List[str]) -> bool:
        key = f"{self.test_prefix}:handoffs:{task_id}"
        handoff = {
            "task_id": task_id,
            "agent_id": self.agent_id,
            "summary": summary,
            "next_steps": next_steps,
            "created_at": time.time()
        }
        start = time.time()
        try:
            self.redis_client.hset(key, mapping={
                "summary": summary,
                "next_steps": json.dumps(next_steps),
                "agent_id": self.agent_id,
                "created_at": str(time.time())
            })
            self.operations.append({
                "type": "create_handoff",
                "task_id": task_id,
                "latency_ms": (time.time() - start) * 1000,
                "success": True
            })
            return True
        except Exception as e:
            self.errors.append(f"create_handoff failed: {e}")
            return False

    def get_handoff(self, task_id: str) -> Dict[str, Any]:
        key = f"{self.test_prefix}:handoffs:{task_id}"
        start = time.time()
        try:
            data = self.redis_client.hgetall(key)
            if data:
                data["next_steps"] = json.loads(data.get("next_steps", "[]"))
            self.operations.append({
                "type": "get_handoff",
                "task_id": task_id,
                "found": bool(data),
                "latency_ms": (time.time() - start) * 1000,
                "success": True
            })
            return data
        except Exception as e:
            self.errors.append(f"get_handoff failed: {e}")
            return {}


@pytest.fixture
def agent_factory(redis_client: redis.Redis, stress_test_id: str):
    agents = []

    def create_agent(agent_id: str = None) -> AgentSimulator:
        aid = agent_id or f"agent-{uuid.uuid4().hex[:8]}"
        agent = AgentSimulator(
            agent_id=aid,
            redis_client=redis_client,
            test_prefix=stress_test_id
        )
        agents.append(agent)
        return agent

    yield create_agent

    for key in redis_client.scan_iter(f"{stress_test_id}:*"):
        redis_client.delete(key)


@dataclass
class LockSimulator:
    redis_client: redis.Redis
    test_prefix: str
    agent_id: str
    held_locks: List[str] = field(default_factory=list)

    def acquire(self, file_path: str, ttl: int = 300) -> bool:
        key = f"{self.test_prefix}:locks:{file_path.replace('/', ':')}"
        lock_data = json.dumps({
            "agent_id": self.agent_id,
            "file_path": file_path,
            "acquired_at": time.time()
        })
        acquired = self.redis_client.set(key, lock_data, nx=True, ex=ttl)
        if acquired:
            self.held_locks.append(file_path)
        return bool(acquired)

    def release(self, file_path: str) -> bool:
        key = f"{self.test_prefix}:locks:{file_path.replace('/', ':')}"
        existing = self.redis_client.get(key)
        if existing:
            data = json.loads(existing)
            if data.get("agent_id") == self.agent_id:
                self.redis_client.delete(key)
                if file_path in self.held_locks:
                    self.held_locks.remove(file_path)
                return True
        return False

    def is_locked(self, file_path: str) -> bool:
        key = f"{self.test_prefix}:locks:{file_path.replace('/', ':')}"
        return self.redis_client.exists(key) > 0

    def get_owner(self, file_path: str) -> str:
        key = f"{self.test_prefix}:locks:{file_path.replace('/', ':')}"
        data = self.redis_client.get(key)
        if data:
            return json.loads(data).get("agent_id", "")
        return ""


@pytest.fixture
def lock_factory(redis_client: redis.Redis, stress_test_id: str):
    locks = []

    def create_lock(agent_id: str) -> LockSimulator:
        lock = LockSimulator(
            redis_client=redis_client,
            test_prefix=stress_test_id,
            agent_id=agent_id
        )
        locks.append(lock)
        return lock

    yield create_lock

    for key in redis_client.scan_iter(f"{stress_test_id}:locks:*"):
        redis_client.delete(key)


@dataclass
class TaskSimulator:
    redis_client: redis.Redis
    test_prefix: str

    CLAIM_SCRIPT = """
    local task_key = KEYS[1]
    local claim_key = KEYS[2]
    local queue_key = KEYS[3]
    local agent_id = ARGV[1]
    local task_id = ARGV[2]
    local timestamp = ARGV[3]
    local dep_keys_json = ARGV[4]

    if redis.call('EXISTS', claim_key) == 1 then
        return {false, 'already_claimed'}
    end

    local dep_keys = cjson.decode(dep_keys_json)
    for i, dep_key in ipairs(dep_keys) do
        local dep_data = redis.call('GET', dep_key)
        if not dep_data then
            return {false, 'missing_dependency'}
        end
        local dep = cjson.decode(dep_data)
        if dep.status ~= 'completed' then
            return {false, 'dependency_not_completed'}
        end
    end

    local result = redis.call('SET', claim_key, agent_id, 'EX', 3600, 'NX')
    if not result then
        return {false, 'already_claimed'}
    end

    local task_data = redis.call('GET', task_key)
    if task_data then
        local task = cjson.decode(task_data)
        task.status = 'claimed'
        task.assigned_to = agent_id
        task.started_at = timestamp
        redis.call('SET', task_key, cjson.encode(task))
    end

    redis.call('ZREM', queue_key, task_id)

    return {true, 'claimed'}
    """

    def __post_init__(self):
        self._claim_script = self.redis_client.register_script(self.CLAIM_SCRIPT)

    def create_task(self, task_id: str, title: str, deps: List[str] = None, priority: int = 5) -> Dict:
        task = {
            "id": task_id,
            "title": title,
            "status": "pending",
            "deps": deps or [],
            "priority": priority,
            "created_at": time.time()
        }
        task_key = f"{self.test_prefix}:tasks:{task_id}"
        queue_key = f"{self.test_prefix}:queue"
        self.redis_client.set(task_key, json.dumps(task))
        self.redis_client.zadd(queue_key, {task_id: priority})
        return task

    def claim_task(self, task_id: str, agent_id: str) -> tuple:
        task_key = f"{self.test_prefix}:tasks:{task_id}"
        claim_key = f"{self.test_prefix}:claims:{task_id}"
        queue_key = f"{self.test_prefix}:queue"

        task_data = self.redis_client.get(task_key)
        if not task_data:
            return False, "task_not_found"

        task = json.loads(task_data)
        dep_keys = [f"{self.test_prefix}:tasks:{d}" for d in task.get("deps", [])]

        result = self._claim_script(
            keys=[task_key, claim_key, queue_key],
            args=[agent_id, task_id, str(time.time()), json.dumps(dep_keys)]
        )
        return bool(result[0]), result[1].decode() if isinstance(result[1], bytes) else result[1]

    def complete_task(self, task_id: str, agent_id: str) -> bool:
        task_key = f"{self.test_prefix}:tasks:{task_id}"
        claim_key = f"{self.test_prefix}:claims:{task_id}"

        owner = self.redis_client.get(claim_key)
        if owner != agent_id:
            return False

        task_data = self.redis_client.get(task_key)
        if task_data:
            task = json.loads(task_data)
            task["status"] = "completed"
            task["completed_at"] = time.time()
            self.redis_client.set(task_key, json.dumps(task))
            self.redis_client.delete(claim_key)
            return True
        return False

    def get_task(self, task_id: str) -> Dict:
        task_key = f"{self.test_prefix}:tasks:{task_id}"
        data = self.redis_client.get(task_key)
        return json.loads(data) if data else {}

    def get_queue_size(self) -> int:
        queue_key = f"{self.test_prefix}:queue"
        return self.redis_client.zcard(queue_key)


@pytest.fixture
def task_simulator(redis_client: redis.Redis, stress_test_id: str) -> Generator[TaskSimulator, None, None]:
    sim = TaskSimulator(redis_client=redis_client, test_prefix=stress_test_id)
    yield sim
    for key in redis_client.scan_iter(f"{stress_test_id}:tasks:*"):
        redis_client.delete(key)
    for key in redis_client.scan_iter(f"{stress_test_id}:claims:*"):
        redis_client.delete(key)
    redis_client.delete(f"{stress_test_id}:queue")


@pytest.fixture
def cleanup_stress_keys(redis_client: redis.Redis, stress_test_id: str):
    yield
    for key in redis_client.scan_iter(f"{stress_test_id}:*"):
        redis_client.delete(key)
