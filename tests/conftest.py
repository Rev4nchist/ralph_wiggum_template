"""Shared pytest fixtures for Ralph Wiggum tests."""

import json
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import Generator

import pytest

# Add lib directories to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib" / "ralph-client"))
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

try:
    import fakeredis
    FAKEREDIS_AVAILABLE = True
except ImportError:
    FAKEREDIS_AVAILABLE = False
    fakeredis = None


@pytest.fixture
def mock_redis():
    """Create a fake Redis client for testing."""
    if not FAKEREDIS_AVAILABLE:
        pytest.skip("fakeredis not installed")
    return fakeredis.FakeStrictRedis(decode_responses=True)


@pytest.fixture
def mock_redis_bytes():
    """Create a fake Redis client that returns bytes (for Lua scripts)."""
    if not FAKEREDIS_AVAILABLE:
        pytest.skip("fakeredis not installed")
    return fakeredis.FakeStrictRedis(decode_responses=False)


@pytest.fixture
def agent_id():
    """Default test agent ID."""
    return "test-agent-001"


@pytest.fixture
def other_agent_id():
    """Another agent ID for multi-agent tests."""
    return "test-agent-002"


@pytest.fixture
def task_queue(mock_redis, agent_id):
    """Create a TaskQueue instance with mock Redis."""
    from tasks import TaskQueue
    return TaskQueue(mock_redis, agent_id)


@pytest.fixture
def file_lock(mock_redis, agent_id):
    """Create a FileLock instance with mock Redis."""
    from locks import FileLock
    return FileLock(mock_redis, agent_id)


@pytest.fixture
def agent_registry(mock_redis, agent_id):
    """Create an AgentRegistry instance with mock Redis."""
    from registry import AgentRegistry
    return AgentRegistry(mock_redis, agent_id, "test", ["implement", "debug"])


@pytest.fixture
def sample_task_data():
    """Sample task data for testing."""
    return {
        "id": "task-001",
        "title": "Implement feature X",
        "description": "Add feature X to module Y",
        "task_type": "implement",
        "priority": 5,
        "status": "pending",
        "files": ["src/module.py"],
        "dependencies": [],
        "wait_for": [],
        "acceptance_criteria": ["Tests pass", "No linting errors"],
    }


@pytest.fixture
def completed_task_data():
    """A completed task for dependency testing."""
    return {
        "id": "task-dep-001",
        "title": "Dependency task",
        "description": "This task is completed",
        "task_type": "implement",
        "priority": 5,
        "status": "completed",
        "files": [],
        "dependencies": [],
        "wait_for": [],
    }


@pytest.fixture
def pending_task_data():
    """A pending task for dependency testing."""
    return {
        "id": "task-dep-002",
        "title": "Pending dependency",
        "description": "This task is not yet done",
        "task_type": "implement",
        "priority": 5,
        "status": "pending",
        "files": [],
        "dependencies": [],
        "wait_for": [],
    }


@pytest.fixture
def mock_subprocess():
    """Mock subprocess.run for command execution tests."""
    with patch("subprocess.run") as mock:
        mock.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr=""
        )
        yield mock


@pytest.fixture
def mock_time():
    """Mock time.time for TTL tests."""
    with patch("time.time", return_value=1704067200.0):  # 2024-01-01 00:00:00
        yield


class MockPubSub:
    """Mock Redis Pub/Sub for message testing."""

    def __init__(self):
        self.subscriptions = []
        self.messages = []

    def subscribe(self, *channels):
        self.subscriptions.extend(channels)

    def listen(self):
        for msg in self.messages:
            yield msg

    def add_message(self, channel, data):
        self.messages.append({
            "type": "message",
            "channel": channel,
            "data": json.dumps(data) if isinstance(data, dict) else data
        })


@pytest.fixture
def mock_pubsub():
    """Create a mock Pub/Sub instance."""
    return MockPubSub()


# === Integration Test Fixtures ===

PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="session")
def project_root():
    """Return project root path."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def redis_available():
    """Check if Redis is available for tests."""
    try:
        import redis as real_redis
        client = real_redis.Redis(host='localhost', port=6379, db=0)
        client.ping()
        client.close()
        return True
    except Exception:
        return False


@pytest.fixture
def skip_if_no_redis(redis_available):
    """Skip test if Redis is not available."""
    if not redis_available:
        pytest.skip("Redis not available")


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "requires_redis: marks tests that require Redis connection"
    )
    config.addinivalue_line(
        "markers", "e2e: marks end-to-end tests"
    )
    config.addinivalue_line(
        "markers", "slow: marks slow-running tests"
    )


def pytest_collection_modifyitems(config, items):
    """Add markers based on test location."""
    for item in items:
        if "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
        if "memory" in str(item.fspath):
            item.add_marker(pytest.mark.requires_redis)
