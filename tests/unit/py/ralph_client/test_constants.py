"""Tests for constants module."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "lib" / "ralph-client"))

from constants import RedisKeys, TaskStatusConst, TaskTypeConst, Defaults


class TestRedisKeys:
    """P2 Medium: Redis key pattern tests."""

    @pytest.mark.p2
    def test_task_key_generation(self):
        """task() generates correct key pattern."""
        key = RedisKeys.task("abc123")
        assert key == "ralph:tasks:data:abc123"

    @pytest.mark.p2
    def test_task_claimed_key_generation(self):
        """task_claimed() generates correct key pattern."""
        key = RedisKeys.task_claimed("abc123")
        assert key == "ralph:tasks:claimed:abc123"

    @pytest.mark.p2
    def test_tasks_by_status_key_generation(self):
        """tasks_by_status() generates correct key pattern."""
        key = RedisKeys.tasks_by_status("pending")
        assert key == "ralph:tasks:by_status:pending"

    @pytest.mark.p2
    def test_lock_key_generation(self):
        """lock() generates correct key pattern."""
        key = RedisKeys.lock("src/main.py")
        assert key == "ralph:locks:file:src/main.py"

    @pytest.mark.p2
    def test_heartbeat_key_generation(self):
        """heartbeat() generates correct key pattern."""
        key = RedisKeys.heartbeat("agent-001")
        assert key == "ralph:heartbeats:agent-001"

    @pytest.mark.p2
    def test_messages_key_generation(self):
        """messages() generates correct key pattern."""
        key = RedisKeys.messages("agent-001")
        assert key == "ralph:messages:agent-001"


class TestTaskStatusConst:
    """P2 Medium: Task status constant tests."""

    @pytest.mark.p2
    def test_all_statuses_defined(self):
        """All expected status values are defined."""
        assert TaskStatusConst.PENDING == "pending"
        assert TaskStatusConst.CLAIMED == "claimed"
        assert TaskStatusConst.IN_PROGRESS == "in_progress"
        assert TaskStatusConst.BLOCKED == "blocked"
        assert TaskStatusConst.COMPLETED == "completed"
        assert TaskStatusConst.FAILED == "failed"


class TestDefaults:
    """P2 Medium: Default configuration tests."""

    @pytest.mark.p2
    def test_heartbeat_defaults(self):
        """Heartbeat defaults are reasonable."""
        assert Defaults.HEARTBEAT_TTL == 15
        assert Defaults.HEARTBEAT_INTERVAL == 5
        assert Defaults.HEARTBEAT_TTL > Defaults.HEARTBEAT_INTERVAL

    @pytest.mark.p2
    def test_task_claim_ttl(self):
        """Task claim TTL is 1 hour."""
        assert Defaults.TASK_CLAIM_TTL == 3600

    @pytest.mark.p2
    def test_lock_ttl(self):
        """Lock TTL is 5 minutes."""
        assert Defaults.LOCK_TTL == 300

    @pytest.mark.p2
    def test_orphan_threshold(self):
        """Orphan threshold is 5 minutes."""
        assert Defaults.ORPHAN_THRESHOLD_SECONDS == 300
