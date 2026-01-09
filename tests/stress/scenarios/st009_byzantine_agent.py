"""
ST-009: Byzantine Agent Test

Tests system resilience when agents send malformed or malicious data.
Verifies graceful degradation and isolation of bad actors.

Pass Criteria:
- System doesn't crash on bad data
- Bad data rejected/sanitized
- Other agents unaffected
- Errors logged clearly
"""
import pytest
import time
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
from dataclasses import dataclass, field

from ..conftest import requires_redis


MAX_CONTENT_SIZE = 10 * 1024
MAX_FIELD_LENGTH = 1000


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)
    sanitized_data: Optional[Dict] = None


class DataValidator:

    @staticmethod
    def validate_task_result(data: any) -> ValidationResult:
        errors = []

        if not isinstance(data, dict):
            try:
                data = json.loads(data) if isinstance(data, str) else {}
            except json.JSONDecodeError:
                return ValidationResult(False, ["Invalid JSON"])

        if "task_id" not in data:
            errors.append("Missing task_id")
        elif not isinstance(data["task_id"], str):
            errors.append("task_id must be string")
        elif len(data["task_id"]) > MAX_FIELD_LENGTH:
            errors.append("task_id too long")

        if "result" in data:
            result_str = json.dumps(data["result"])
            if len(result_str) > MAX_CONTENT_SIZE:
                errors.append(f"Result too large: {len(result_str)} bytes")

        if "content" in data and isinstance(data["content"], str):
            if "\x00" in data["content"]:
                errors.append("Null bytes in content")
                data["content"] = data["content"].replace("\x00", "")

        if errors:
            return ValidationResult(False, errors)

        return ValidationResult(True, [], data)

    @staticmethod
    def validate_memory_content(content: str) -> ValidationResult:
        errors = []

        if not isinstance(content, str):
            return ValidationResult(False, ["Content must be string"])

        if len(content) > MAX_CONTENT_SIZE:
            errors.append(f"Content too large: {len(content)} bytes")

        if "\x00" in content:
            errors.append("Null bytes detected")
            content = content.replace("\x00", "")

        dangerous_patterns = ["<script", "javascript:", "data:text/html"]
        for pattern in dangerous_patterns:
            if pattern.lower() in content.lower():
                errors.append(f"Dangerous pattern detected: {pattern}")

        if errors:
            return ValidationResult(False, errors, {"sanitized": content})

        return ValidationResult(True, [], {"content": content})

    @staticmethod
    def validate_handoff(data: any) -> ValidationResult:
        errors = []

        if not isinstance(data, dict):
            return ValidationResult(False, ["Handoff must be dict"])

        required = ["from_task", "to_task", "context"]
        for field in required:
            if field not in data:
                errors.append(f"Missing required field: {field}")

        if "context" in data:
            try:
                context_str = json.dumps(data["context"])
                if len(context_str) > MAX_CONTENT_SIZE:
                    errors.append("Context too large")
            except (TypeError, ValueError):
                errors.append("Context not serializable")

        if errors:
            return ValidationResult(False, errors)

        return ValidationResult(True, [], data)


class ResilientTaskStore:

    def __init__(self, redis_client, prefix: str):
        self.redis = redis_client
        self.prefix = prefix
        self.errors_key = f"{prefix}:errors"
        self.tasks_key = f"{prefix}:tasks"
        self.validator = DataValidator()

    def store_result(self, data: any) -> bool:
        validation = self.validator.validate_task_result(data)

        if not validation.valid:
            self._log_error("task_result", validation.errors, data)
            return False

        task_id = validation.sanitized_data["task_id"]
        self.redis.hset(
            self.tasks_key,
            task_id,
            json.dumps(validation.sanitized_data)
        )
        return True

    def _log_error(self, error_type: str, errors: List[str], raw_data: any):
        error_entry = {
            "type": error_type,
            "errors": errors,
            "timestamp": time.time(),
            "data_preview": str(raw_data)[:200]
        }
        self.redis.lpush(self.errors_key, json.dumps(error_entry))
        self.redis.ltrim(self.errors_key, 0, 999)

    def get_errors(self, limit: int = 100) -> List[Dict]:
        errors = self.redis.lrange(self.errors_key, 0, limit - 1)
        return [json.loads(e) for e in errors]


class ResilientMemoryStore:

    def __init__(self, redis_client, prefix: str):
        self.redis = redis_client
        self.prefix = prefix
        self.memories_key = f"{prefix}:memories"
        self.errors_key = f"{prefix}:memory_errors"
        self.validator = DataValidator()

    def store(self, agent_id: str, content: str, category: str) -> Optional[str]:
        validation = self.validator.validate_memory_content(content)

        if not validation.valid:
            self._log_error(agent_id, validation.errors, content)
            return None

        memory_id = f"mem-{int(time.time() * 1000000)}"
        safe_content = validation.sanitized_data.get("content", content)

        memory = {
            "id": memory_id,
            "agent_id": agent_id,
            "content": safe_content,
            "category": category,
            "timestamp": time.time()
        }

        self.redis.hset(self.memories_key, memory_id, json.dumps(memory))
        return memory_id

    def _log_error(self, agent_id: str, errors: List[str], content: str):
        error_entry = {
            "agent_id": agent_id,
            "errors": errors,
            "timestamp": time.time(),
            "content_preview": content[:100] if content else ""
        }
        self.redis.lpush(self.errors_key, json.dumps(error_entry))

    def get_errors(self) -> List[Dict]:
        errors = self.redis.lrange(self.errors_key, 0, -1)
        return [json.loads(e) for e in errors]


@requires_redis
class TestByzantineAgent:

    def test_invalid_json_handling(
        self,
        redis_client,
        stress_test_id
    ):
        """
        ST-009: System handles invalid JSON gracefully.
        """
        store = ResilientTaskStore(redis_client, stress_test_id)

        invalid_data = [
            "not json at all",
            "{incomplete json",
            "{'single': 'quotes'}",
            None,
            12345,
            ["array", "not", "object"]
        ]

        for data in invalid_data:
            result = store.store_result(data)
            assert not result, f"Should reject invalid data: {data}"

        errors = store.get_errors()
        assert len(errors) >= len(invalid_data), \
            f"Should log all errors: {len(errors)} < {len(invalid_data)}"

    def test_oversized_content_rejected(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Oversized content (10MB+) should be rejected.
        """
        store = ResilientMemoryStore(redis_client, f"{stress_test_id}:oversize")

        huge_content = "x" * (MAX_CONTENT_SIZE + 1000)
        result = store.store(
            "byzantine-agent",
            huge_content,
            "test"
        )

        assert result is None, "Should reject oversized content"

        errors = store.get_errors()
        assert any("too large" in str(e) for e in errors), \
            "Should log size error"

    def test_null_bytes_sanitized(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Null bytes in content should be stripped.
        """
        validator = DataValidator()

        content_with_nulls = "Hello\x00World\x00Test"
        result = validator.validate_memory_content(content_with_nulls)

        assert not result.valid, "Should flag null bytes"
        assert "Null bytes" in str(result.errors)
        assert "\x00" not in result.sanitized_data.get("sanitized", "")

    def test_script_injection_blocked(
        self,
        redis_client,
        stress_test_id
    ):
        """
        XSS-like patterns should be rejected.
        """
        store = ResilientMemoryStore(redis_client, f"{stress_test_id}:xss")

        malicious_content = [
            "<script>alert('xss')</script>",
            "javascript:alert(1)",
            "data:text/html,<script>evil()</script>",
        ]

        for content in malicious_content:
            result = store.store("evil-agent", content, "test")
            assert result is None, f"Should reject: {content[:30]}"

    def test_wrong_task_id_rejected(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Task results with wrong task_id format rejected.
        """
        store = ResilientTaskStore(redis_client, f"{stress_test_id}:wrongid")

        bad_task_ids = [
            {"task_id": 12345, "result": "ok"},
            {"task_id": None, "result": "ok"},
            {"task_id": "x" * 2000, "result": "ok"},
            {"result": "ok"},
        ]

        for data in bad_task_ids:
            result = store.store_result(data)
            assert not result, f"Should reject: {data}"

    def test_normal_agents_unaffected(
        self,
        redis_client,
        stress_test_id,
        thread_pool_10
    ):
        """
        Byzantine agents don't affect normal agents.
        """
        store = ResilientMemoryStore(redis_client, f"{stress_test_id}:isolation")

        results = {"good": [], "bad": []}
        lock = threading.Lock()

        def good_agent(agent_id: str, count: int):
            stored = []
            for i in range(count):
                mem_id = store.store(
                    agent_id,
                    f"Normal memory {i} from {agent_id}",
                    "normal"
                )
                if mem_id:
                    stored.append(mem_id)
            with lock:
                results["good"].extend(stored)

        def bad_agent(agent_id: str, count: int):
            stored = []
            bad_content = [
                "x" * (MAX_CONTENT_SIZE + 100),
                "Content\x00with\x00nulls",
                "<script>evil()</script>",
                "data:text/html,bad"
            ]
            for i in range(count):
                content = bad_content[i % len(bad_content)]
                mem_id = store.store(agent_id, content, "bad")
                if mem_id:
                    stored.append(mem_id)
            with lock:
                results["bad"].extend(stored)

        futures = []
        for i in range(5):
            futures.append(thread_pool_10.submit(good_agent, f"good-{i}", 20))

        for i in range(3):
            futures.append(thread_pool_10.submit(bad_agent, f"bad-{i}", 20))

        for f in as_completed(futures, timeout=30):
            f.result()

        assert len(results["good"]) == 100, \
            f"Good agents should store 100 memories: {len(results['good'])}"

        assert len(results["bad"]) < 60, \
            f"Bad agents should have rejections: {len(results['bad'])}"

    def test_handoff_validation(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Invalid handoffs rejected gracefully.
        """
        validator = DataValidator()

        invalid_handoffs = [
            "not a dict",
            {"from_task": "A"},
            {"from_task": "A", "to_task": "B"},
            {
                "from_task": "A",
                "to_task": "B",
                "context": {"circular": None}
            }
        ]

        invalid_handoffs[3]["context"]["circular"] = invalid_handoffs[3]["context"]

        for i, handoff in enumerate(invalid_handoffs[:3]):
            result = validator.validate_handoff(handoff)
            assert not result.valid, f"Should reject handoff {i}"

    def test_error_logging_bounded(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Error logs don't grow unbounded.
        """
        store = ResilientTaskStore(redis_client, f"{stress_test_id}:bounded")

        for i in range(1500):
            store.store_result(f"invalid-{i}")

        errors = store.get_errors(limit=2000)
        assert len(errors) <= 1000, \
            f"Error log should be bounded: {len(errors)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
