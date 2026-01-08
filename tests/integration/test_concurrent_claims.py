"""Integration tests for concurrent task claiming.

Tests race condition prevention in the TaskQueue.claim() method.
Since fakeredis doesn't support Lua scripts (EVALSHA), these tests
mock the Lua script while testing the concurrency logic.

For true integration testing with real Redis and Lua scripts,
use the run-integration-test.sh script with a real Redis instance.
"""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lib" / "ralph-client"))

try:
    import fakeredis
    FAKEREDIS_AVAILABLE = True
except ImportError:
    FAKEREDIS_AVAILABLE = False

from tasks import TaskQueue, Task, TaskStatus


pytestmark = pytest.mark.integration


def create_mock_claim_script(redis_client, claim_lock: threading.Lock):
    """Create a mock claim script that simulates atomic behavior with a lock."""
    def mock_script(keys, args):
        task_key = keys[0]
        claim_key = keys[1]
        queue_key = keys[2]
        agent_id = args[0]
        dep_keys_json = args[1]
        wait_keys_json = args[2]
        task_id = args[3]
        timestamp = args[4]

        with claim_lock:
            if redis_client.exists(claim_key):
                return [False, b'already_claimed']

            dep_keys = json.loads(dep_keys_json)
            for dep_key in dep_keys:
                dep_data = redis_client.get(dep_key)
                if not dep_data:
                    return [False, b'missing_dependency']
                dep = json.loads(dep_data)
                if dep.get('status') != 'completed':
                    return [False, b'dependency_not_completed']

            wait_keys = json.loads(wait_keys_json)
            for wait_key in wait_keys:
                wait_data = redis_client.get(wait_key)
                if not wait_data:
                    return [False, b'missing_wait_task']
                wait_task = json.loads(wait_data)
                if wait_task.get('status') != 'completed':
                    return [False, b'wait_task_not_completed']

            redis_client.set(claim_key, agent_id, ex=3600)

            task_data = redis_client.get(task_key)
            if task_data:
                task = json.loads(task_data)
                task['status'] = 'claimed'
                task['assigned_to'] = agent_id if isinstance(agent_id, str) else agent_id.decode()
                task['started_at'] = timestamp if isinstance(timestamp, str) else timestamp.decode()
                redis_client.set(task_key, json.dumps(task))

            redis_client.zrem(queue_key, task_id)

            return [True, b'claimed']

    return mock_script


@pytest.fixture
def redis():
    """Create a fake Redis instance."""
    if not FAKEREDIS_AVAILABLE:
        pytest.skip("fakeredis not installed")
    server = fakeredis.FakeServer()
    return fakeredis.FakeStrictRedis(server=server, decode_responses=False)


@pytest.fixture
def claim_lock():
    """Shared lock for atomic claim simulation."""
    return threading.Lock()


@pytest.fixture
def task_queue(redis, claim_lock):
    """Create a TaskQueue with mock claim script."""
    queue = TaskQueue(redis, agent_id='test-coordinator')
    queue._claim_script = MagicMock(side_effect=create_mock_claim_script(redis, claim_lock))
    return queue


class TestConcurrentTaskClaiming:
    """Tests for race condition prevention in task claiming."""

    def test_only_one_agent_claims_task(self, redis, claim_lock):
        """Verify exactly one agent wins the race when 10 try simultaneously."""
        task_id = 'race-test-task'
        task_data = {
            'id': task_id,
            'title': 'Test concurrent claim',
            'description': 'A task that many agents want',
            'status': 'pending',
            'priority': 5,
            'task_type': 'implement',
            'dependencies': [],
            'wait_for': [],
            'files': [],
            'acceptance_criteria': [],
            'created_at': time.time(),
        }
        redis.set(f'ralph:tasks:data:{task_id}'.encode(), json.dumps(task_data).encode())
        redis.zadd('ralph:tasks:queue', {task_id.encode(): 5})

        claim_results: List[Tuple[int, bool]] = []
        results_lock = threading.Lock()

        def try_claim(agent_num: int) -> bool:
            queue = TaskQueue(redis, agent_id=f'agent-{agent_num}')
            queue._claim_script = MagicMock(side_effect=create_mock_claim_script(redis, claim_lock))
            task = queue.get(task_id)
            if task:
                success = queue.claim(task)
                with results_lock:
                    claim_results.append((agent_num, success))
                return success
            return False

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(try_claim, i) for i in range(10)]
            for f in as_completed(futures):
                pass

        successful = sum(1 for _, success in claim_results if success)

        assert successful == 1, f"Expected 1 successful claim, got {successful}"

    def test_claim_preserves_task_data(self, task_queue, redis):
        """Verify task data integrity after claim."""
        task_id = 'data-test-task'
        original_title = 'Important Task'
        original_desc = 'Testing data integrity'

        task = Task(
            id=task_id,
            title=original_title,
            description=original_desc,
            status='pending',
            priority=8,
            task_type='backend'
        )
        task_queue.enqueue(task)

        retrieved = task_queue.get(task_id)
        assert task_queue.claim(retrieved)

        stored = redis.get(f'ralph:tasks:data:{task_id}'.encode())
        data = json.loads(stored)

        assert data['title'] == original_title
        assert data['description'] == original_desc
        assert data['status'] == 'claimed'
        assert data['assigned_to'] == task_queue.agent_id

    def test_rapid_claim_release_cycles(self, redis, claim_lock):
        """Test rapid claim/release doesn't corrupt state."""
        task_id = 'cycle-test-task'

        task_data = {
            'id': task_id,
            'title': 'Cycle test',
            'description': 'Test rapid cycles',
            'status': 'pending',
            'priority': 5,
            'task_type': 'implement',
            'dependencies': [],
            'wait_for': [],
            'files': [],
            'acceptance_criteria': [],
        }
        redis.set(f'ralph:tasks:data:{task_id}'.encode(), json.dumps(task_data).encode())
        redis.zadd('ralph:tasks:queue', {task_id.encode(): 5})

        queue = TaskQueue(redis, agent_id='cycler')
        queue._claim_script = MagicMock(side_effect=create_mock_claim_script(redis, claim_lock))

        for i in range(20):
            task = queue.get(task_id)
            if task and task.status == 'pending':
                claimed = queue.claim(task)
                if claimed:
                    queue.release_claim(task_id)

        final_data = redis.get(f'ralph:tasks:data:{task_id}'.encode())
        final = json.loads(final_data)

        assert final['status'] == 'pending'

    def test_claim_removes_from_queue(self, task_queue, redis):
        """Verify claimed task is removed from the priority queue."""
        task = Task(
            id='queue-removal-test',
            title='Queue removal test',
            description='Test queue removal on claim',
            priority=5
        )
        task_queue.enqueue(task)

        in_queue_before = redis.zscore('ralph:tasks:queue', b'queue-removal-test')
        assert in_queue_before is not None

        retrieved = task_queue.get('queue-removal-test')
        task_queue.claim(retrieved)

        in_queue_after = redis.zscore('ralph:tasks:queue', b'queue-removal-test')
        assert in_queue_after is None

    def test_concurrent_claims_different_tasks(self, redis, claim_lock):
        """Multiple agents can claim different tasks simultaneously."""
        for i in range(5):
            task_data = {
                'id': f'task-{i}',
                'title': f'Task {i}',
                'description': 'Parallel claim test',
                'status': 'pending',
                'priority': 5,
                'task_type': 'implement',
                'dependencies': [],
                'wait_for': [],
            }
            redis.set(f'ralph:tasks:data:task-{i}'.encode(), json.dumps(task_data).encode())
            redis.zadd('ralph:tasks:queue', {f'task-{i}'.encode(): 5})

        claim_results: List[Tuple[str, str, bool]] = []
        results_lock = threading.Lock()

        def claim_task(agent_id: str, task_id: str) -> bool:
            queue = TaskQueue(redis, agent_id=agent_id)
            queue._claim_script = MagicMock(side_effect=create_mock_claim_script(redis, claim_lock))
            task = queue.get(task_id)
            if task:
                success = queue.claim(task)
                with results_lock:
                    claim_results.append((agent_id, task_id, success))
                return success
            return False

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(claim_task, f'agent-{i}', f'task-{i}')
                for i in range(5)
            ]
            for f in as_completed(futures):
                pass

        successful = sum(1 for _, _, success in claim_results if success)

        assert successful == 5, f"Expected 5 successful claims (different tasks), got {successful}"


class TestClaimWithDependencies:
    """Tests for claiming tasks with dependencies."""

    @pytest.fixture
    def redis(self):
        if not FAKEREDIS_AVAILABLE:
            pytest.skip("fakeredis not installed")
        server = fakeredis.FakeServer()
        return fakeredis.FakeStrictRedis(server=server, decode_responses=False)

    @pytest.fixture
    def claim_lock(self):
        return threading.Lock()

    def test_cannot_claim_with_incomplete_dependency(self, redis, claim_lock):
        """Task with incomplete dependency should not be claimable."""
        dep_task = {
            'id': 'dep-task',
            'title': 'Dependency',
            'description': 'Not yet completed',
            'status': 'pending',
            'priority': 5,
            'task_type': 'implement',
            'dependencies': [],
            'wait_for': [],
        }
        redis.set(b'ralph:tasks:data:dep-task', json.dumps(dep_task).encode())

        main_task = {
            'id': 'main-task',
            'title': 'Main Task',
            'description': 'Depends on dep-task',
            'status': 'pending',
            'priority': 5,
            'task_type': 'implement',
            'dependencies': ['dep-task'],
            'wait_for': [],
        }
        redis.set(b'ralph:tasks:data:main-task', json.dumps(main_task).encode())
        redis.zadd('ralph:tasks:queue', {b'main-task': 5})

        queue = TaskQueue(redis, agent_id='claimer')
        queue._claim_script = MagicMock(side_effect=create_mock_claim_script(redis, claim_lock))
        task = queue.get('main-task')

        result = queue.claim(task)
        assert not result, "Should not claim task with incomplete dependency"

    def test_can_claim_with_completed_dependency(self, redis, claim_lock):
        """Task with completed dependency should be claimable."""
        dep_task = {
            'id': 'dep-task-complete',
            'title': 'Completed Dependency',
            'description': 'Already done',
            'status': 'completed',
            'priority': 5,
            'task_type': 'implement',
            'dependencies': [],
            'wait_for': [],
        }
        redis.set(b'ralph:tasks:data:dep-task-complete', json.dumps(dep_task).encode())

        main_task = {
            'id': 'main-task-ready',
            'title': 'Ready Task',
            'description': 'Dependencies satisfied',
            'status': 'pending',
            'priority': 5,
            'task_type': 'implement',
            'dependencies': ['dep-task-complete'],
            'wait_for': [],
        }
        redis.set(b'ralph:tasks:data:main-task-ready', json.dumps(main_task).encode())
        redis.zadd('ralph:tasks:queue', {b'main-task-ready': 5})

        queue = TaskQueue(redis, agent_id='claimer')
        queue._claim_script = MagicMock(side_effect=create_mock_claim_script(redis, claim_lock))
        task = queue.get('main-task-ready')

        result = queue.claim(task)
        assert result, "Should claim task with completed dependency"

    def test_cannot_claim_with_missing_dependency(self, redis, claim_lock):
        """Task referencing non-existent dependency should not be claimable."""
        main_task = {
            'id': 'orphan-task',
            'title': 'Orphan Task',
            'description': 'Depends on ghost task',
            'status': 'pending',
            'priority': 5,
            'task_type': 'implement',
            'dependencies': ['nonexistent-task'],
            'wait_for': [],
        }
        redis.set(b'ralph:tasks:data:orphan-task', json.dumps(main_task).encode())
        redis.zadd('ralph:tasks:queue', {b'orphan-task': 5})

        queue = TaskQueue(redis, agent_id='claimer')
        queue._claim_script = MagicMock(side_effect=create_mock_claim_script(redis, claim_lock))
        task = queue.get('orphan-task')

        result = queue.claim(task)
        assert not result, "Should not claim task with missing dependency"

    def test_wait_for_blocks_claim(self, redis, claim_lock):
        """Task with incomplete wait_for should not be claimable."""
        wait_task = {
            'id': 'wait-task',
            'title': 'Wait Task',
            'description': 'Soft dependency in progress',
            'status': 'in_progress',
            'priority': 5,
            'task_type': 'implement',
            'dependencies': [],
            'wait_for': [],
        }
        redis.set(b'ralph:tasks:data:wait-task', json.dumps(wait_task).encode())

        blocked_task = {
            'id': 'blocked-task',
            'title': 'Blocked Task',
            'description': 'Waiting for wait-task',
            'status': 'pending',
            'priority': 5,
            'task_type': 'implement',
            'dependencies': [],
            'wait_for': ['wait-task'],
        }
        redis.set(b'ralph:tasks:data:blocked-task', json.dumps(blocked_task).encode())
        redis.zadd('ralph:tasks:queue', {b'blocked-task': 5})

        queue = TaskQueue(redis, agent_id='claimer')
        queue._claim_script = MagicMock(side_effect=create_mock_claim_script(redis, claim_lock))
        task = queue.get('blocked-task')

        result = queue.claim(task)
        assert not result, "Should not claim task with incomplete wait_for"

    def test_chain_dependency_resolution(self, redis, claim_lock):
        """Chain of dependencies must all be completed."""
        task_a = {
            'id': 'task-a',
            'title': 'Task A',
            'status': 'completed',
            'priority': 5,
            'task_type': 'implement',
            'description': 'First in chain',
            'dependencies': [],
            'wait_for': [],
        }
        redis.set(b'ralph:tasks:data:task-a', json.dumps(task_a).encode())

        task_b = {
            'id': 'task-b',
            'title': 'Task B',
            'status': 'completed',
            'priority': 5,
            'task_type': 'implement',
            'description': 'Second in chain',
            'dependencies': ['task-a'],
            'wait_for': [],
        }
        redis.set(b'ralph:tasks:data:task-b', json.dumps(task_b).encode())

        task_c = {
            'id': 'task-c',
            'title': 'Task C',
            'status': 'pending',
            'priority': 5,
            'task_type': 'implement',
            'description': 'Third in chain',
            'dependencies': ['task-b'],
            'wait_for': [],
        }
        redis.set(b'ralph:tasks:data:task-c', json.dumps(task_c).encode())
        redis.zadd('ralph:tasks:queue', {b'task-c': 5})

        queue = TaskQueue(redis, agent_id='chain-claimer')
        queue._claim_script = MagicMock(side_effect=create_mock_claim_script(redis, claim_lock))
        task = queue.get('task-c')

        result = queue.claim(task)
        assert result, "Should claim task when entire dependency chain is complete"


class TestClaimStateTransitions:
    """Tests for task state transitions during claiming."""

    @pytest.fixture
    def redis(self):
        if not FAKEREDIS_AVAILABLE:
            pytest.skip("fakeredis not installed")
        server = fakeredis.FakeServer()
        return fakeredis.FakeStrictRedis(server=server, decode_responses=False)

    @pytest.fixture
    def claim_lock(self):
        return threading.Lock()

    def test_claim_sets_started_at_timestamp(self, redis, claim_lock):
        """Claiming a task should set started_at timestamp."""
        task_data = {
            'id': 'timestamp-task',
            'title': 'Timestamp Test',
            'description': 'Test timestamp setting',
            'status': 'pending',
            'priority': 5,
            'task_type': 'implement',
            'dependencies': [],
            'wait_for': [],
        }
        redis.set(b'ralph:tasks:data:timestamp-task', json.dumps(task_data).encode())
        redis.zadd('ralph:tasks:queue', {b'timestamp-task': 5})

        queue = TaskQueue(redis, agent_id='timestamper')
        queue._claim_script = MagicMock(side_effect=create_mock_claim_script(redis, claim_lock))
        task = queue.get('timestamp-task')
        queue.claim(task)

        stored = redis.get(b'ralph:tasks:data:timestamp-task')
        data = json.loads(stored)

        assert 'started_at' in data
        assert data['started_at'] is not None

    def test_cannot_reclaim_claimed_task(self, redis, claim_lock):
        """A task already claimed cannot be claimed again."""
        task_data = {
            'id': 'no-reclaim-task',
            'title': 'No Reclaim',
            'description': 'Should not be reclaimable',
            'status': 'pending',
            'priority': 5,
            'task_type': 'implement',
            'dependencies': [],
            'wait_for': [],
        }
        redis.set(b'ralph:tasks:data:no-reclaim-task', json.dumps(task_data).encode())
        redis.zadd('ralph:tasks:queue', {b'no-reclaim-task': 5})

        queue1 = TaskQueue(redis, agent_id='first-claimer')
        queue1._claim_script = MagicMock(side_effect=create_mock_claim_script(redis, claim_lock))
        task1 = queue1.get('no-reclaim-task')
        first_claim = queue1.claim(task1)

        queue2 = TaskQueue(redis, agent_id='second-claimer')
        queue2._claim_script = MagicMock(side_effect=create_mock_claim_script(redis, claim_lock))
        task2 = queue2.get('no-reclaim-task')
        if task2:
            second_claim = queue2.claim(task2)
        else:
            second_claim = False

        assert first_claim, "First claim should succeed"
        assert not second_claim, "Second claim should fail"

    def test_release_allows_reclaim(self, redis, claim_lock):
        """Released task can be claimed by another agent."""
        task_data = {
            'id': 'release-reclaim-task',
            'title': 'Release and Reclaim',
            'description': 'Test release then reclaim',
            'status': 'pending',
            'priority': 5,
            'task_type': 'implement',
            'dependencies': [],
            'wait_for': [],
        }
        redis.set(b'ralph:tasks:data:release-reclaim-task', json.dumps(task_data).encode())
        redis.zadd('ralph:tasks:queue', {b'release-reclaim-task': 5})

        queue1 = TaskQueue(redis, agent_id='first-agent')
        queue1._claim_script = MagicMock(side_effect=create_mock_claim_script(redis, claim_lock))
        task1 = queue1.get('release-reclaim-task')
        queue1.claim(task1)
        queue1.release_claim('release-reclaim-task')

        queue2 = TaskQueue(redis, agent_id='second-agent')
        queue2._claim_script = MagicMock(side_effect=create_mock_claim_script(redis, claim_lock))
        task2 = queue2.get('release-reclaim-task')
        second_claim = queue2.claim(task2)

        assert second_claim, "Second agent should be able to claim after release"
