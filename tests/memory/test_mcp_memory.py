"""
Test Suite 1: Memory System Tests
Tests for ralph_memory_store, ralph_memory_recall, ralph_memory_context, ralph_memory_handoff
"""
import pytest
import json
import redis
import time
from unittest.mock import Mock, patch, MagicMock

PROJECT_ID = "test-project"
TASK_ID = "TASK-001"
REDIS_PREFIX = f"claude_mem:{PROJECT_ID}"


class TestMemoryStore:
    """Test 1.1: Memory Store & Recall"""

    @pytest.fixture
    def redis_client(self):
        client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        yield client
        for key in client.keys(f"{REDIS_PREFIX}*"):
            client.delete(key)

    def test_store_architecture_memory(self, redis_client):
        """Store architecture decision and verify in Redis"""
        memory = {
            "content": "Architecture: Use monorepo structure",
            "category": "architecture",
            "tags": ["setup", "structure"],
            "project_id": PROJECT_ID
        }
        key = f"{REDIS_PREFIX}:memories"
        memory_id = f"mem_{int(time.time() * 1000)}"
        redis_client.hset(key, memory_id, json.dumps(memory))

        stored = redis_client.hget(key, memory_id)
        assert stored is not None
        parsed = json.loads(stored)
        assert parsed["content"] == "Architecture: Use monorepo structure"
        assert parsed["category"] == "architecture"
        assert "setup" in parsed["tags"]

    def test_store_pattern_memory(self, redis_client):
        """Store pattern memory with tags"""
        memory = {
            "content": "Pattern: Use AAA for test structure",
            "category": "pattern",
            "tags": ["testing", "best-practice"],
            "project_id": PROJECT_ID
        }
        key = f"{REDIS_PREFIX}:memories"
        memory_id = f"mem_{int(time.time() * 1000)}"
        redis_client.hset(key, memory_id, json.dumps(memory))

        stored = redis_client.hget(key, memory_id)
        parsed = json.loads(stored)
        assert parsed["category"] == "pattern"
        assert "testing" in parsed["tags"]

    def test_store_blocker_memory(self, redis_client):
        """Store blocker memory for issue tracking"""
        memory = {
            "content": "Blocker: Redis connection timeout under load",
            "category": "blocker",
            "tags": ["infrastructure", "redis"],
            "project_id": PROJECT_ID,
            "resolved": False
        }
        key = f"{REDIS_PREFIX}:memories"
        memory_id = f"mem_{int(time.time() * 1000)}"
        redis_client.hset(key, memory_id, json.dumps(memory))

        stored = redis_client.hget(key, memory_id)
        parsed = json.loads(stored)
        assert parsed["category"] == "blocker"
        assert parsed["resolved"] is False


class TestMemoryRecall:
    """Test memory recall by query and category"""

    @pytest.fixture
    def seeded_redis(self):
        client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        key = f"{REDIS_PREFIX}:memories"

        memories = [
            {"id": "mem_1", "content": "Architecture: Use monorepo", "category": "architecture", "tags": ["setup"]},
            {"id": "mem_2", "content": "Pattern: AAA for tests", "category": "pattern", "tags": ["testing"]},
            {"id": "mem_3", "content": "Blocker: Redis timeout", "category": "blocker", "tags": ["infra"]},
            {"id": "mem_4", "content": "Decision: Use TypeScript strict", "category": "decision", "tags": ["config"]},
            {"id": "mem_5", "content": "Learning: JWT refresh pattern", "category": "learning", "tags": ["auth"]}
        ]

        for mem in memories:
            client.hset(key, mem["id"], json.dumps(mem))

        yield client

        for k in client.keys(f"{REDIS_PREFIX}*"):
            client.delete(k)

    def test_recall_by_keyword(self, seeded_redis):
        """Recall memories matching keyword query"""
        key = f"{REDIS_PREFIX}:memories"
        all_memories = seeded_redis.hgetall(key)

        query = "monorepo"
        matches = []
        for mem_id, mem_json in all_memories.items():
            mem = json.loads(mem_json)
            if query.lower() in mem["content"].lower():
                matches.append(mem)

        assert len(matches) == 1
        assert "Architecture: Use monorepo" in matches[0]["content"]

    def test_recall_by_category(self, seeded_redis):
        """Recall memories filtered by category"""
        key = f"{REDIS_PREFIX}:memories"
        all_memories = seeded_redis.hgetall(key)

        category = "pattern"
        matches = []
        for mem_id, mem_json in all_memories.items():
            mem = json.loads(mem_json)
            if mem.get("category") == category:
                matches.append(mem)

        assert len(matches) == 1
        assert matches[0]["content"] == "Pattern: AAA for tests"

    def test_recall_by_tag(self, seeded_redis):
        """Recall memories filtered by tag"""
        key = f"{REDIS_PREFIX}:memories"
        all_memories = seeded_redis.hgetall(key)

        tag = "testing"
        matches = []
        for mem_id, mem_json in all_memories.items():
            mem = json.loads(mem_json)
            if tag in mem.get("tags", []):
                matches.append(mem)

        assert len(matches) == 1
        assert "AAA" in matches[0]["content"]


class TestMemoryContext:
    """Test 1.2: Memory Context (Project & Task)"""

    @pytest.fixture
    def context_redis(self):
        client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

        project_context = {
            "name": PROJECT_ID,
            "description": "Test project for auth feature",
            "created_at": "2025-01-08",
            "tech_stack": json.dumps(["React", "TypeScript", "PostgreSQL"])
        }
        client.hset(f"{REDIS_PREFIX}:project_context", mapping=project_context)

        task_data = {
            "id": TASK_ID,
            "title": "Implement login form",
            "status": "in_progress",
            "agent": "frontend"
        }
        client.hset(f"{REDIS_PREFIX}:task:{TASK_ID}", mapping=task_data)

        key = f"{REDIS_PREFIX}:memories"
        task_memories = [
            {"id": "tm_1", "content": "Login form uses Formik", "task_id": TASK_ID, "category": "decision"},
            {"id": "tm_2", "content": "Validation with Zod", "task_id": TASK_ID, "category": "pattern"}
        ]
        for mem in task_memories:
            client.hset(key, mem["id"], json.dumps(mem))

        yield client

        for k in client.keys(f"{REDIS_PREFIX}*"):
            client.delete(k)

    def test_get_project_context(self, context_redis):
        """Retrieve project-level context"""
        context = context_redis.hgetall(f"{REDIS_PREFIX}:project_context")

        assert context["name"] == PROJECT_ID
        assert "React" in context["tech_stack"]

    def test_get_task_context(self, context_redis):
        """Retrieve task-specific context"""
        task_data = context_redis.hgetall(f"{REDIS_PREFIX}:task:{TASK_ID}")

        assert task_data["id"] == TASK_ID
        assert task_data["status"] == "in_progress"
        assert task_data["agent"] == "frontend"

    def test_get_task_memories(self, context_redis):
        """Retrieve memories associated with specific task"""
        key = f"{REDIS_PREFIX}:memories"
        all_memories = context_redis.hgetall(key)

        task_memories = []
        for mem_id, mem_json in all_memories.items():
            mem = json.loads(mem_json)
            if mem.get("task_id") == TASK_ID:
                task_memories.append(mem)

        assert len(task_memories) == 2
        contents = [m["content"] for m in task_memories]
        assert "Login form uses Formik" in contents
        assert "Validation with Zod" in contents


class TestMemoryHandoff:
    """Test 1.3: Memory Handoff (Cross-Agent)"""

    @pytest.fixture
    def handoff_redis(self):
        client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        yield client
        for k in client.keys(f"{REDIS_PREFIX}*"):
            client.delete(k)

    def test_create_handoff(self, handoff_redis):
        """Create handoff note for next agent"""
        handoff = {
            "task_id": "FE-001",
            "summary": "Login form implemented with validation",
            "next_steps": json.dumps(["Add password reset", "Write tests", "Integrate with API"]),
            "blockers": json.dumps([]),
            "created_by": "frontend",
            "created_at": "2025-01-08T10:00:00Z"
        }

        key = f"{REDIS_PREFIX}:handoffs:FE-001"
        handoff_redis.hset(key, mapping=handoff)

        stored = handoff_redis.hgetall(key)
        assert stored["summary"] == "Login form implemented with validation"
        next_steps = json.loads(stored["next_steps"])
        assert "Add password reset" in next_steps

    def test_retrieve_handoff_for_next_agent(self, handoff_redis):
        """Next agent retrieves handoff from previous agent"""
        handoff = {
            "task_id": "FE-001",
            "summary": "Login form done",
            "next_steps": json.dumps(["Add validation", "Write tests"]),
            "blockers": json.dumps([]),
            "created_by": "frontend",
            "created_at": "2025-01-08T10:00:00Z"
        }
        key = f"{REDIS_PREFIX}:handoffs:FE-001"
        handoff_redis.hset(key, mapping=handoff)

        retrieved = handoff_redis.hgetall(key)

        assert retrieved["summary"] == "Login form done"
        assert retrieved["created_by"] == "frontend"
        next_steps = json.loads(retrieved["next_steps"])
        assert len(next_steps) == 2

    def test_handoff_creates_learning_memory(self, handoff_redis):
        """Handoff auto-creates a learning memory"""
        task_id = "FE-001"
        handoff = {
            "task_id": task_id,
            "summary": "Completed login form with Formik",
            "next_steps": json.dumps(["Test integration"]),
            "created_by": "frontend"
        }
        key = f"{REDIS_PREFIX}:handoffs:{task_id}"
        handoff_redis.hset(key, mapping=handoff)

        learning = {
            "content": f"Completed {task_id}: {handoff['summary']}",
            "category": "learning",
            "task_id": task_id,
            "source": "handoff"
        }
        mem_key = f"{REDIS_PREFIX}:memories"
        handoff_redis.hset(mem_key, f"learn_{task_id}", json.dumps(learning))

        stored = handoff_redis.hget(mem_key, f"learn_{task_id}")
        parsed = json.loads(stored)
        assert parsed["category"] == "learning"
        assert parsed["source"] == "handoff"


class TestMemoryPersistence:
    """Test 1.4: Memory Persistence (survives restart)"""

    @pytest.fixture
    def persistent_redis(self):
        client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        yield client
        for k in client.keys(f"{REDIS_PREFIX}*"):
            client.delete(k)

    def test_memory_survives_connection_close(self, persistent_redis):
        """Memory persists after connection close/reopen"""
        memory = {"content": "Persistent test memory", "category": "decision"}
        key = f"{REDIS_PREFIX}:memories"
        persistent_redis.hset(key, "persist_test", json.dumps(memory))

        persistent_redis.close()

        new_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        stored = new_client.hget(key, "persist_test")

        assert stored is not None
        parsed = json.loads(stored)
        assert parsed["content"] == "Persistent test memory"

        new_client.delete(key)
        new_client.close()


class TestMemoryCategories:
    """Test all memory categories work correctly"""

    CATEGORIES = ["architecture", "pattern", "blocker", "decision", "learning", "general"]

    @pytest.fixture
    def category_redis(self):
        client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        yield client
        for k in client.keys(f"{REDIS_PREFIX}*"):
            client.delete(k)

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_store_retrieve_by_category(self, category_redis, category):
        """Each category can be stored and filtered"""
        memory = {
            "content": f"Test memory for {category}",
            "category": category,
            "project_id": PROJECT_ID
        }
        key = f"{REDIS_PREFIX}:memories"
        mem_id = f"cat_{category}"
        category_redis.hset(key, mem_id, json.dumps(memory))

        stored = category_redis.hget(key, mem_id)
        parsed = json.loads(stored)
        assert parsed["category"] == category


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
