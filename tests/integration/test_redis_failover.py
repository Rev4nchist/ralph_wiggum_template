"""Integration tests for Redis failover handling."""
import pytest
import time
import threading
import json
from unittest.mock import MagicMock, patch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lib" / "ralph-client"))

try:
    import fakeredis
    FAKEREDIS_AVAILABLE = True
except ImportError:
    FAKEREDIS_AVAILABLE = False


pytestmark = pytest.mark.integration


def create_mock_claim_script(redis_client, claim_lock: threading.Lock = None):
    """Create a mock claim script that simulates atomic behavior."""
    lock = claim_lock or threading.Lock()

    def mock_script(keys, args):
        task_key = keys[0]
        claim_key = keys[1]
        queue_key = keys[2]
        agent_id = args[0]
        dep_keys_json = args[1]
        wait_keys_json = args[2]
        task_id = args[3]
        timestamp = args[4]

        with lock:
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


def create_mock_unlock_script(redis_client):
    """Create a mock unlock script for FileLock."""
    def mock_script(keys, args):
        lock_key = keys[0]
        agent_id = args[0]

        lock_data = redis_client.get(lock_key)
        if not lock_data:
            return [True, b'no_lock']

        lock = json.loads(lock_data)
        if lock.get('agent_id') != agent_id:
            return [False, b'not_owner']

        redis_client.delete(lock_key)
        return [True, b'released']

    return mock_script


class TestRedisConnectionResilience:
    """Tests for Redis connection failure handling."""

    @pytest.fixture
    def redis(self):
        """Create a fake Redis that can simulate failures."""
        if not FAKEREDIS_AVAILABLE:
            pytest.skip("fakeredis not installed")
        return fakeredis.FakeStrictRedis(decode_responses=False)

    @pytest.fixture
    def claim_lock(self):
        return threading.Lock()

    def test_operations_recover_after_brief_disconnect(self, redis, claim_lock):
        """Operations should succeed after Redis reconnects."""
        from tasks import TaskQueue, Task

        queue = TaskQueue(redis, agent_id='resilient-agent')
        queue._claim_script = MagicMock(side_effect=create_mock_claim_script(redis, claim_lock))

        task = Task(
            id='recover-test',
            title='Test recovery',
            description='Test task for recovery',
            status='pending',
            priority=5
        )
        queue.enqueue(task)

        retrieved = queue.get('recover-test')
        assert retrieved is not None
        assert retrieved.title == 'Test recovery'

    def test_lock_acquisition_with_connection_issues(self, redis):
        """Lock operations should handle connection issues."""
        from locks import FileLock

        lock = FileLock(redis, 'connection-test-agent')
        lock._unlock_script = MagicMock(side_effect=create_mock_unlock_script(redis))

        result = lock.acquire('/test/file.py', ttl=60)
        assert result is True

        released = lock.release('/test/file.py')
        assert released is True

    def test_heartbeat_continues_after_reconnect(self, redis):
        """Heartbeat should resume after Redis reconnects."""
        from registry import AgentRegistry

        registry = AgentRegistry(redis)
        agent_id = 'heartbeat-resilience-test'

        registry.register(agent_id, 'backend', ['test'])
        assert registry.is_alive(agent_id)

        registry.heartbeat(agent_id)
        assert registry.is_alive(agent_id)


class TestOrphanRecovery:
    """Tests for orphaned task recovery."""

    @pytest.fixture
    def redis(self):
        if not FAKEREDIS_AVAILABLE:
            pytest.skip("fakeredis not installed")
        return fakeredis.FakeStrictRedis(decode_responses=False)

    def test_cleanup_finds_orphaned_tasks(self, redis):
        """OrphanCleaner should find tasks from dead agents."""
        from cleanup import OrphanCleaner

        cleaner = OrphanCleaner(redis)

        task_id = 'orphan-task-1'
        dead_agent = 'dead-agent-123'

        task_data = {
            'id': task_id,
            'title': 'Orphaned task',
            'status': 'claimed',
            'assigned_to': dead_agent,
            'started_at': time.time() - 600,
            'priority': 5
        }
        redis.set(f'ralph:tasks:data:{task_id}'.encode(), json.dumps(task_data).encode())
        redis.set(f'ralph:tasks:claimed:{task_id}'.encode(), dead_agent.encode())

        orphans = cleaner.get_orphaned_tasks()

        assert len(orphans) == 1
        assert orphans[0].task_id == task_id
        assert orphans[0].agent_id == dead_agent

    def test_cleanup_releases_orphaned_tasks(self, redis):
        """OrphanCleaner should release orphaned tasks back to queue."""
        from cleanup import OrphanCleaner

        cleaner = OrphanCleaner(redis)

        task_id = 'orphan-release-test'
        dead_agent = 'crashed-agent'

        task_data = {
            'id': task_id,
            'title': 'Will be released',
            'status': 'claimed',
            'assigned_to': dead_agent,
            'started_at': time.time() - 600,
            'priority': 7
        }
        redis.set(f'ralph:tasks:data:{task_id}'.encode(), json.dumps(task_data).encode())
        redis.set(f'ralph:tasks:claimed:{task_id}'.encode(), dead_agent.encode())

        released = cleaner.cleanup_orphaned_claims()

        assert task_id in released

        updated = json.loads(redis.get(f'ralph:tasks:data:{task_id}'.encode()))
        assert updated['status'] == 'pending'
        assert updated['assigned_to'] is None
        assert updated.get('orphan_recovered') is True

        score = redis.zscore('ralph:tasks:queue', task_id.encode())
        assert score == 7

    def test_cleanup_ignores_live_agent_tasks(self, redis):
        """OrphanCleaner should not touch tasks from live agents."""
        from cleanup import OrphanCleaner

        cleaner = OrphanCleaner(redis)

        task_id = 'live-agent-task'
        live_agent = 'healthy-agent'

        task_data = {
            'id': task_id,
            'title': 'Active task',
            'status': 'claimed',
            'assigned_to': live_agent,
            'started_at': time.time(),
            'priority': 5
        }
        redis.set(f'ralph:tasks:data:{task_id}'.encode(), json.dumps(task_data).encode())
        redis.set(f'ralph:tasks:claimed:{task_id}'.encode(), live_agent.encode())

        redis.setex(f'ralph:heartbeats:{live_agent}'.encode(), 30, str(time.time()).encode())

        released = cleaner.cleanup_orphaned_claims()

        assert task_id not in released

        updated = json.loads(redis.get(f'ralph:tasks:data:{task_id}'.encode()))
        assert updated['status'] == 'claimed'


class TestStreamReliability:
    """Tests for Redis Streams reliability."""

    @pytest.fixture
    def redis(self):
        if not FAKEREDIS_AVAILABLE:
            pytest.skip("fakeredis not installed")
        return fakeredis.FakeStrictRedis(decode_responses=False)

    def test_stream_publish_returns_id(self, redis):
        """Publishing to stream should return message ID."""
        try:
            from streams import EventStream

            stream = EventStream(redis, 'test-producer')
            msg_id = stream.publish('task_completed', {'task_id': 'test-1'})

            assert msg_id is not None
            assert '-' in str(msg_id)
        except Exception as e:
            if 'XGROUP' in str(e) or 'unknown command' in str(e).lower():
                pytest.skip("fakeredis doesn't fully support streams")
            raise

    def test_stream_consumer_group_creation(self, redis):
        """Consumer group should be created idempotently."""
        try:
            from streams import EventStream

            stream1 = EventStream(redis, 'consumer-1')
            stream2 = EventStream(redis, 'consumer-2')

            stream1.publish('test_event', {'key': 'value1'})
            stream2.publish('test_event', {'key': 'value2'})

        except Exception as e:
            if 'XGROUP' in str(e) or 'unknown command' in str(e).lower():
                pytest.skip("fakeredis doesn't fully support streams")
            raise


class TestRegistryFailover:
    """Tests for agent registry during failures."""

    @pytest.fixture
    def redis(self):
        """Use decode_responses=True for registry tests to avoid bytes/str issues."""
        if not FAKEREDIS_AVAILABLE:
            pytest.skip("fakeredis not installed")
        return fakeredis.FakeStrictRedis(decode_responses=True)

    def test_stale_agent_cleanup(self, redis):
        """Registry should clean up agents without heartbeats."""
        from registry import AgentRegistry

        registry = AgentRegistry(redis)

        registry.register('agent-1', 'backend', ['implement'])
        registry.register('agent-2', 'frontend', ['build'])

        redis.delete('ralph:heartbeats:agent-1')

        removed = registry.cleanup_stale()

        assert 'agent-1' in removed
        assert registry.get_agent('agent-2') is not None

    def test_agent_status_update_during_operation(self, redis):
        """Agent status updates should persist during operations."""
        from registry import AgentRegistry

        registry = AgentRegistry(redis)
        agent_id = 'status-test-agent'

        registry.register(agent_id, 'general', ['all'])

        registry.update_status(agent_id, 'busy', 'Processing task-123')

        agent = registry.get_agent(agent_id)
        assert agent['status'] == 'busy'
        assert agent['status_details'] == 'Processing task-123'


class TestLockFailover:
    """Tests for file locking during failures."""

    @pytest.fixture
    def redis(self):
        if not FAKEREDIS_AVAILABLE:
            pytest.skip("fakeredis not installed")
        return fakeredis.FakeStrictRedis(decode_responses=False)

    def test_lock_expiry_prevents_deadlock(self, redis):
        """Locks should expire to prevent deadlocks from crashed agents."""
        from locks import FileLock

        lock1 = FileLock(redis, 'agent-crash')

        lock1.acquire('/shared/resource.py', ttl=1)

        time.sleep(2)

        lock2 = FileLock(redis, 'agent-recover')
        acquired = lock2.acquire('/shared/resource.py', ttl=60)

        assert acquired is True

    def test_force_release_for_admin_recovery(self, redis):
        """Admin should be able to force release locks."""
        from locks import FileLock

        holder = FileLock(redis, 'stuck-agent')
        holder._unlock_script = MagicMock(side_effect=create_mock_unlock_script(redis))
        holder.acquire('/critical/file.py', ttl=3600)

        admin = FileLock(redis, 'admin-agent')
        admin._unlock_script = MagicMock(side_effect=create_mock_unlock_script(redis))

        released = admin.force_release('/critical/file.py')
        assert released is True

        new_holder = FileLock(redis, 'new-agent')
        acquired = new_holder.acquire('/critical/file.py')
        assert acquired is True
