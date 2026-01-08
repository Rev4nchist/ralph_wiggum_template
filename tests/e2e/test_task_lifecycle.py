"""End-to-end tests for complete task lifecycle."""
import pytest
import json
import time
import threading
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lib" / "ralph-client"))

try:
    import fakeredis
    FAKEREDIS_AVAILABLE = True
except ImportError:
    FAKEREDIS_AVAILABLE = False


pytestmark = pytest.mark.integration


def create_mock_claim_script_str(redis_client, claim_lock: threading.Lock = None):
    """Create a mock claim script for decode_responses=True Redis."""
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
                return [False, 'already_claimed']

            dep_keys = json.loads(dep_keys_json)
            for dep_key in dep_keys:
                dep_data = redis_client.get(dep_key)
                if not dep_data:
                    return [False, 'missing_dependency']
                dep = json.loads(dep_data)
                if dep.get('status') != 'completed':
                    return [False, 'dependency_not_completed']

            wait_keys = json.loads(wait_keys_json)
            for wait_key in wait_keys:
                wait_data = redis_client.get(wait_key)
                if not wait_data:
                    return [False, 'missing_wait_task']
                wait_task = json.loads(wait_data)
                if wait_task.get('status') != 'completed':
                    return [False, 'wait_task_not_completed']

            redis_client.set(claim_key, agent_id, ex=3600)

            task_data = redis_client.get(task_key)
            if task_data:
                task = json.loads(task_data)
                task['status'] = 'claimed'
                task['assigned_to'] = agent_id
                task['started_at'] = timestamp
                redis_client.set(task_key, json.dumps(task))

            redis_client.zrem(queue_key, task_id)

            return [True, 'claimed']

    return mock_script


def create_mock_unlock_script_str(redis_client):
    """Create a mock unlock script for decode_responses=True Redis."""
    def mock_script(keys, args):
        lock_key = keys[0]
        agent_id = args[0]

        lock_data = redis_client.get(lock_key)
        if not lock_data:
            return [True, 'no_lock']

        lock = json.loads(lock_data)
        if lock.get('agent_id') != agent_id:
            return [False, 'not_owner']

        redis_client.delete(lock_key)
        return [True, 'released']

    return mock_script


class TestCompleteTaskLifecycle:
    """E2E tests for task creation through completion."""

    @pytest.fixture
    def redis(self):
        if not FAKEREDIS_AVAILABLE:
            pytest.skip("fakeredis not installed")
        server = fakeredis.FakeServer()
        return fakeredis.FakeStrictRedis(server=server, decode_responses=True)

    @pytest.fixture
    def claim_lock(self):
        return threading.Lock()

    def test_task_create_claim_complete_lifecycle(self, redis, claim_lock):
        """Test full lifecycle: create -> claim -> complete."""
        from tasks import TaskQueue, Task
        from registry import AgentRegistry

        registry = AgentRegistry(redis)
        coordinator = TaskQueue(redis, agent_id='coordinator')
        worker = TaskQueue(redis, agent_id='worker-1')

        coordinator._claim_script = create_mock_claim_script_str(redis, claim_lock)
        worker._claim_script = create_mock_claim_script_str(redis, claim_lock)

        registry.register('worker-1', 'backend', ['implement'])

        task = Task(
            id='lifecycle-test',
            title='Build feature X',
            description='Implement the feature',
            status='pending',
            priority=8,
            task_type='backend'
        )
        coordinator.enqueue(task)

        available = worker.get_next()
        assert available is not None
        assert available.id == 'lifecycle-test'

        claimed = worker.claim(available)
        assert claimed is True

        updated = worker.get('lifecycle-test')
        assert updated.status == 'claimed'
        assert updated.assigned_to == 'worker-1'

        worker.complete('lifecycle-test', result={'files_changed': 3})

        final = coordinator.get('lifecycle-test')
        assert final.status == 'completed'
        assert final.result['files_changed'] == 3

    def test_task_with_dependencies_lifecycle(self, redis, claim_lock):
        """Test lifecycle with task dependencies."""
        from tasks import TaskQueue, Task

        queue = TaskQueue(redis, agent_id='dep-worker')
        queue._claim_script = create_mock_claim_script_str(redis, claim_lock)

        dep_task = Task(
            id='dep-task',
            title='Setup database',
            description='Initialize database schema',
            status='pending',
            priority=9
        )
        queue.enqueue(dep_task)

        main_task = Task(
            id='main-task',
            title='Run migrations',
            description='Execute database migrations',
            status='pending',
            priority=8,
            dependencies=['dep-task']
        )
        queue.enqueue(main_task)

        main = queue.get('main-task')
        assert queue.claim(main) is False

        dep = queue.get('dep-task')
        queue.claim(dep)
        queue.complete('dep-task', result={'success': True})

        main = queue.get('main-task')
        assert queue.claim(main) is True

    def test_failed_task_lifecycle(self, redis, claim_lock):
        """Test lifecycle when task fails."""
        from tasks import TaskQueue, Task

        queue = TaskQueue(redis, agent_id='failing-worker')
        queue._claim_script = create_mock_claim_script_str(redis, claim_lock)

        task = Task(
            id='failing-task',
            title='Risky operation',
            description='An operation that may fail',
            status='pending',
            priority=5
        )
        queue.enqueue(task)

        t = queue.get('failing-task')
        queue.claim(t)

        queue.fail('failing-task', error='Connection timeout')

        failed = queue.get('failing-task')
        assert failed.status == 'failed'
        assert 'Connection timeout' in str(failed.error)


class TestMultiAgentWorkflow:
    """E2E tests for multi-agent coordination."""

    @pytest.fixture
    def redis(self):
        if not FAKEREDIS_AVAILABLE:
            pytest.skip("fakeredis not installed")
        server = fakeredis.FakeServer()
        return fakeredis.FakeStrictRedis(server=server, decode_responses=True)

    @pytest.fixture
    def claim_lock(self):
        return threading.Lock()

    def test_multiple_agents_process_queue(self, redis, claim_lock):
        """Multiple agents should process different tasks."""
        from tasks import TaskQueue, Task
        from registry import AgentRegistry

        registry = AgentRegistry(redis)
        coordinator = TaskQueue(redis, agent_id='coordinator')
        coordinator._claim_script = create_mock_claim_script_str(redis, claim_lock)

        for i in range(5):
            task = Task(
                id=f'multi-task-{i}',
                title=f'Task {i}',
                description=f'Task number {i}',
                status='pending',
                priority=5
            )
            coordinator.enqueue(task)

        workers = []
        for i in range(3):
            agent_id = f'worker-{i}'
            registry.register(agent_id, 'general', ['work'])
            queue = TaskQueue(redis, agent_id=agent_id)
            queue._claim_script = create_mock_claim_script_str(redis, claim_lock)
            workers.append(queue)

        claimed_tasks = []
        for worker in workers:
            task = worker.get_next()
            if task and worker.claim(task):
                claimed_tasks.append(task.id)

        assert len(claimed_tasks) == 3
        assert len(set(claimed_tasks)) == 3

    def test_file_locking_between_agents(self, redis):
        """Agents should respect file locks."""
        from locks import FileLock
        from registry import AgentRegistry

        registry = AgentRegistry(redis)

        registry.register('agent-a', 'frontend', ['edit'])
        registry.register('agent-b', 'frontend', ['edit'])

        lock_a = FileLock(redis, 'agent-a')
        lock_b = FileLock(redis, 'agent-b')

        lock_a._unlock_script = create_mock_unlock_script_str(redis)
        lock_b._unlock_script = create_mock_unlock_script_str(redis)

        file_path = '/src/component.tsx'

        assert lock_a.acquire(file_path) is True

        assert lock_b.acquire(file_path) is False

        holder = lock_b.get_lock_owner(file_path)
        assert holder == 'agent-a'

        assert lock_a.release(file_path) is True

        assert lock_b.acquire(file_path) is True


class TestAuthenticatedWorkflow:
    """E2E tests with authentication enabled."""

    @pytest.fixture
    def redis(self):
        if not FAKEREDIS_AVAILABLE:
            pytest.skip("fakeredis not installed")
        return fakeredis.FakeStrictRedis(decode_responses=True)

    def test_agent_registration_with_auth(self, redis):
        """Agents should register and authenticate."""
        from auth import TokenAuth, AuthLevel

        auth = TokenAuth(redis)

        token = auth.register_agent('secure-agent', AuthLevel.AGENT)
        assert token is not None
        assert len(token) == 64

        level = auth.verify('secure-agent', token)
        assert level == AuthLevel.AGENT

        with pytest.raises(Exception):
            auth.verify('secure-agent', 'wrong-token')

    def test_permission_levels(self, redis):
        """Different auth levels should have different permissions."""
        from auth import TokenAuth, AuthLevel

        auth = TokenAuth(redis)

        readonly_token = auth.register_agent('reader', AuthLevel.READONLY)
        agent_token = auth.register_agent('worker', AuthLevel.AGENT)
        admin_token = auth.register_agent('admin', AuthLevel.ADMIN)

        assert auth.check_permission('reader', readonly_token, AuthLevel.READONLY) is True
        assert auth.check_permission('reader', readonly_token, AuthLevel.AGENT) is False

        assert auth.check_permission('worker', agent_token, AuthLevel.AGENT) is True
        assert auth.check_permission('worker', agent_token, AuthLevel.ADMIN) is False

        assert auth.check_permission('admin', admin_token, AuthLevel.ADMIN) is True


class TestTaskPriorityWorkflow:
    """E2E tests for task priority handling."""

    @pytest.fixture
    def redis(self):
        if not FAKEREDIS_AVAILABLE:
            pytest.skip("fakeredis not installed")
        server = fakeredis.FakeServer()
        return fakeredis.FakeStrictRedis(server=server, decode_responses=True)

    @pytest.fixture
    def claim_lock(self):
        return threading.Lock()

    def test_high_priority_tasks_processed_first(self, redis, claim_lock):
        """Higher priority tasks should be processed before lower priority."""
        from tasks import TaskQueue, Task

        queue = TaskQueue(redis, agent_id='priority-worker')
        queue._claim_script = create_mock_claim_script_str(redis, claim_lock)

        low_task = Task(
            id='low-priority',
            title='Low priority task',
            description='Not urgent',
            status='pending',
            priority=2
        )
        queue.enqueue(low_task)

        high_task = Task(
            id='high-priority',
            title='High priority task',
            description='Urgent',
            status='pending',
            priority=9
        )
        queue.enqueue(high_task)

        medium_task = Task(
            id='medium-priority',
            title='Medium priority task',
            description='Normal',
            status='pending',
            priority=5
        )
        queue.enqueue(medium_task)

        first = queue.get_next()
        assert first.id == 'high-priority'

        queue.claim(first)
        queue.complete(first.id, result={})

        second = queue.get_next()
        assert second.id == 'medium-priority'


class TestBlockedTaskWorkflow:
    """E2E tests for blocked task handling."""

    @pytest.fixture
    def redis(self):
        if not FAKEREDIS_AVAILABLE:
            pytest.skip("fakeredis not installed")
        server = fakeredis.FakeServer()
        return fakeredis.FakeStrictRedis(server=server, decode_responses=True)

    @pytest.fixture
    def claim_lock(self):
        return threading.Lock()

    def test_task_blocking_and_resumption(self, redis, claim_lock):
        """Task should be blockable and resumable."""
        from tasks import TaskQueue, Task, TaskStatus

        queue = TaskQueue(redis, agent_id='block-worker')
        queue._claim_script = create_mock_claim_script_str(redis, claim_lock)

        task = Task(
            id='blockable-task',
            title='Task that gets blocked',
            description='May encounter blockers',
            status='pending',
            priority=5
        )
        queue.enqueue(task)

        t = queue.get('blockable-task')
        queue.claim(t)

        queue.block('blockable-task', reason='Waiting for external API')

        blocked = queue.get('blockable-task')
        assert blocked.status == 'blocked'
        assert blocked.metadata.get('blocked_reason') == 'Waiting for external API'


class TestReleaseClaimWorkflow:
    """E2E tests for claim release workflow."""

    @pytest.fixture
    def redis(self):
        if not FAKEREDIS_AVAILABLE:
            pytest.skip("fakeredis not installed")
        server = fakeredis.FakeServer()
        return fakeredis.FakeStrictRedis(server=server, decode_responses=True)

    @pytest.fixture
    def claim_lock(self):
        return threading.Lock()

    def test_released_task_can_be_reclaimed(self, redis, claim_lock):
        """Released tasks should return to queue and be reclaimable."""
        from tasks import TaskQueue, Task

        queue1 = TaskQueue(redis, agent_id='agent-release')
        queue2 = TaskQueue(redis, agent_id='agent-reclaim')

        queue1._claim_script = create_mock_claim_script_str(redis, claim_lock)
        queue2._claim_script = create_mock_claim_script_str(redis, claim_lock)

        task = Task(
            id='release-test',
            title='Releasable task',
            description='Can be released',
            status='pending',
            priority=5
        )
        queue1.enqueue(task)

        t = queue1.get('release-test')
        queue1.claim(t)

        claimed = queue1.get('release-test')
        assert claimed.status == 'claimed'
        assert claimed.assigned_to == 'agent-release'

        queue1.release_claim('release-test')

        released = queue1.get('release-test')
        assert released.status == 'pending'
        assert released.assigned_to is None

        t2 = queue2.get('release-test')
        reclaimed = queue2.claim(t2)
        assert reclaimed is True

        final = queue2.get('release-test')
        assert final.assigned_to == 'agent-reclaim'
