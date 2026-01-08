"""P0 Critical Tests: Atomic Task Claiming with Lua Script.

Tests the TaskQueue.claim() method which uses a Lua script to atomically:
1. Check dependencies are completed
2. Check task is not already claimed
3. Claim the task with NX semantics

This prevents race conditions where multiple agents claim the same task.

NOTE: Unit tests mock the Lua script. Integration tests with real Redis
test the actual Lua script behavior.
"""

import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "lib" / "ralph-client"))

from tasks import TaskQueue, Task, TaskStatus


class TestAtomicTaskClaiming:
    """P0 Critical: Atomic task claiming prevents race conditions.

    These tests mock the Lua script since fakeredis doesn't support
    EVALSHA. The actual Lua script is tested in integration tests.
    """

    @pytest.fixture
    def queue(self, mock_redis, agent_id):
        """Create TaskQueue with mocked Lua script."""
        q = TaskQueue(mock_redis, agent_id)
        return q

    @pytest.fixture
    def other_queue(self, mock_redis, other_agent_id):
        """Create another TaskQueue for different agent."""
        return TaskQueue(mock_redis, other_agent_id)

    @pytest.mark.p0
    def test_claim_succeeds_when_no_dependencies(self, queue, mock_redis):
        """Task with no dependencies can be claimed."""
        task = Task(
            id="task-001",
            title="Test task",
            description="A task with no dependencies",
            dependencies=[],
            wait_for=[]
        )
        mock_redis.set(f"ralph:tasks:data:{task.id}", json.dumps(task.to_dict()))

        queue._claim_script = MagicMock(return_value=[True, 'claimed'])
        result = queue.claim(task)

        assert result is True
        queue._claim_script.assert_called_once()

    @pytest.mark.p0
    def test_claim_fails_when_already_claimed(self, queue, mock_redis):
        """Cannot claim a task already claimed by another agent."""
        task = Task(
            id="task-002",
            title="Contested task",
            description="Two agents want this",
            dependencies=[],
            wait_for=[]
        )
        mock_redis.set(f"ralph:tasks:data:{task.id}", json.dumps(task.to_dict()))
        mock_redis.set(f"ralph:tasks:claimed:{task.id}", "other-agent")

        queue._claim_script = MagicMock(return_value=[False, 'already_claimed'])
        result = queue.claim(task)

        assert result is False

    @pytest.mark.p0
    def test_claim_fails_when_dependency_not_completed(self, queue, mock_redis):
        """Cannot claim if dependencies are not completed."""
        dep_task = Task(
            id="dep-task",
            title="Dependency",
            description="Must complete first",
            status=TaskStatus.PENDING.value
        )
        mock_redis.set(f"ralph:tasks:data:{dep_task.id}", json.dumps(dep_task.to_dict()))

        task = Task(
            id="task-003",
            title="Dependent task",
            description="Depends on dep-task",
            dependencies=["dep-task"],
            wait_for=[]
        )
        mock_redis.set(f"ralph:tasks:data:{task.id}", json.dumps(task.to_dict()))

        queue._claim_script = MagicMock(return_value=[False, 'dependency_not_completed'])
        result = queue.claim(task)

        assert result is False

    @pytest.mark.p0
    def test_claim_succeeds_when_dependencies_completed(self, queue, mock_redis):
        """Can claim when all dependencies are completed."""
        dep_task = Task(
            id="dep-complete",
            title="Completed dependency",
            description="Already done",
            status=TaskStatus.COMPLETED.value
        )
        mock_redis.set(f"ralph:tasks:data:{dep_task.id}", json.dumps(dep_task.to_dict()))

        task = Task(
            id="task-004",
            title="Ready task",
            description="Dependencies met",
            dependencies=["dep-complete"],
            wait_for=[]
        )
        mock_redis.set(f"ralph:tasks:data:{task.id}", json.dumps(task.to_dict()))

        queue._claim_script = MagicMock(return_value=[True, 'claimed'])
        result = queue.claim(task)

        assert result is True

    @pytest.mark.p0
    def test_claim_fails_when_wait_for_not_completed(self, queue, mock_redis):
        """Cannot claim if wait_for tasks are not completed."""
        wait_task = Task(
            id="wait-task",
            title="Wait for this",
            description="Soft dependency",
            status=TaskStatus.IN_PROGRESS.value
        )
        mock_redis.set(f"ralph:tasks:data:{wait_task.id}", json.dumps(wait_task.to_dict()))

        task = Task(
            id="task-005",
            title="Waiting task",
            description="Waits for wait-task",
            dependencies=[],
            wait_for=["wait-task"]
        )
        mock_redis.set(f"ralph:tasks:data:{task.id}", json.dumps(task.to_dict()))

        queue._claim_script = MagicMock(return_value=[False, 'wait_task_not_completed'])
        result = queue.claim(task)

        assert result is False

    @pytest.mark.p0
    def test_claim_updates_task_status(self, queue, mock_redis, agent_id):
        """Successful claim updates task status to CLAIMED."""
        task = Task(
            id="task-006",
            title="Status test",
            description="Check status update",
            dependencies=[],
            wait_for=[]
        )
        mock_redis.set(f"ralph:tasks:data:{task.id}", json.dumps(task.to_dict()))

        queue._claim_script = MagicMock(return_value=[True, 'claimed'])
        queue.claim(task)

        stored = json.loads(mock_redis.get(f"ralph:tasks:data:{task.id}"))
        assert stored["status"] == TaskStatus.CLAIMED.value
        assert stored["assigned_to"] == agent_id


class TestTaskQueueOperations:
    """P1 High: Task queue basic operations."""

    @pytest.fixture
    def queue(self, mock_redis, agent_id):
        return TaskQueue(mock_redis, agent_id)

    @pytest.mark.p1
    def test_enqueue_stores_task_data(self, queue, mock_redis):
        """Enqueue stores task JSON in Redis."""
        task = Task(
            id="enq-001",
            title="Enqueue test",
            description="Test enqueue",
        )

        task_id = queue.enqueue(task)

        stored = mock_redis.get(f"ralph:tasks:data:{task_id}")
        assert stored is not None
        data = json.loads(stored)
        assert data["title"] == "Enqueue test"

    @pytest.mark.p1
    def test_enqueue_adds_to_priority_queue(self, queue, mock_redis):
        """Enqueue adds task to sorted set by priority."""
        task = Task(id="enq-002", title="Priority test", description="Test", priority=3)

        queue.enqueue(task)

        members = mock_redis.zrange("ralph:tasks:queue", 0, -1)
        assert "enq-002" in members

    @pytest.mark.p1
    def test_get_returns_task_by_id(self, queue, mock_redis):
        """Get retrieves task by ID."""
        task = Task(id="get-001", title="Get test", description="Test get")
        queue.enqueue(task)

        retrieved = queue.get("get-001")

        assert retrieved is not None
        assert retrieved.title == "Get test"

    @pytest.mark.p1
    def test_complete_updates_status(self, queue, mock_redis, agent_id):
        """Complete marks task as completed with result."""
        task = Task(id="comp-001", title="Complete test", description="Test")
        queue.enqueue(task)
        task.assigned_to = agent_id
        mock_redis.set(f"ralph:tasks:data:{task.id}", json.dumps(task.to_dict()))

        queue.complete("comp-001", {"output": "success"})

        stored = json.loads(mock_redis.get(f"ralph:tasks:data:comp-001"))
        assert stored["status"] == TaskStatus.COMPLETED.value
        assert stored["result"]["output"] == "success"

    @pytest.mark.p1
    def test_fail_updates_status_with_error(self, queue, mock_redis, agent_id):
        """Fail marks task as failed with error message."""
        task = Task(id="fail-001", title="Fail test", description="Test")
        queue.enqueue(task)
        task.assigned_to = agent_id
        mock_redis.set(f"ralph:tasks:data:{task.id}", json.dumps(task.to_dict()))

        queue.fail("fail-001", "Something went wrong")

        stored = json.loads(mock_redis.get(f"ralph:tasks:data:fail-001"))
        assert stored["status"] == TaskStatus.FAILED.value
        assert stored["error"] == "Something went wrong"

    @pytest.mark.p1
    def test_get_next_returns_unclaimed_task(self, queue, mock_redis):
        """get_next returns an unclaimed task from queue."""
        task = Task(id="next-001", title="Next task", description="Test", priority=5)
        queue.enqueue(task)

        next_task = queue.get_next()

        assert next_task is not None
        assert next_task.id == "next-001"

    @pytest.mark.p1
    def test_release_claim_returns_to_queue(self, queue, mock_redis, agent_id):
        """Release claim puts task back in queue."""
        task = Task(id="rel-001", title="Release test", description="Test", priority=5)
        queue.enqueue(task)
        task.assigned_to = agent_id
        mock_redis.set(f"ralph:tasks:data:{task.id}", json.dumps(task.to_dict()))
        mock_redis.zrem("ralph:tasks:queue", task.id)

        queue.release_claim("rel-001")

        members = mock_redis.zrange("ralph:tasks:queue", 0, -1)
        assert "rel-001" in members
        assert not mock_redis.exists(f"ralph:tasks:claimed:rel-001")


class TestTaskDataclass:
    """P2 Medium: Task dataclass serialization."""

    @pytest.mark.p2
    def test_task_to_dict_serializes_all_fields(self):
        """Task.to_dict() includes all fields."""
        task = Task(
            id="ser-001",
            title="Serialize test",
            description="Test serialization",
            priority=3,
            dependencies=["dep-1", "dep-2"]
        )

        data = task.to_dict()

        assert data["id"] == "ser-001"
        assert data["title"] == "Serialize test"
        assert data["priority"] == 3
        assert "dep-1" in data["dependencies"]

    @pytest.mark.p2
    def test_task_from_dict_deserializes(self):
        """Task.from_dict() creates Task from dict."""
        data = {
            "id": "deser-001",
            "title": "Deserialize test",
            "description": "Test",
            "priority": 7,
            "status": "in_progress"
        }

        task = Task.from_dict(data)

        assert task.id == "deser-001"
        assert task.title == "Deserialize test"
        assert task.priority == 7
        assert task.status == "in_progress"
