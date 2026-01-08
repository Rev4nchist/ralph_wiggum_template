"""Task Queue - Distributed task management for agents"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any

import redis


class TaskStatus(Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskType(Enum):
    IMPLEMENT = "implement"
    DEBUG = "debug"
    REVIEW = "review"
    TEST = "test"
    SECURITY = "security"
    REFACTOR = "refactor"
    DOCS = "docs"
    INTEGRATE = "integrate"


@dataclass
class Task:
    """Represents a task in the queue."""
    id: str
    title: str
    description: str
    task_type: str = "implement"
    priority: int = 5
    status: str = TaskStatus.PENDING.value
    assigned_to: Optional[str] = None
    created_by: Optional[str] = None
    project: Optional[str] = None
    files: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    wait_for: List[str] = field(default_factory=list)
    artifacts_from: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    orchestration_id: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'Task':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class TaskQueue:
    """Distributed task queue with priority and dependencies."""

    QUEUE_KEY = "ralph:tasks:queue"
    TASK_PREFIX = "ralph:tasks:data"
    CLAIMED_KEY = "ralph:tasks:claimed"

    # Lua script for atomic claim with dependency checking
    CLAIM_SCRIPT = """
    local task_key = KEYS[1]
    local claim_key = KEYS[2]
    local agent_id = ARGV[1]
    local dep_keys = cjson.decode(ARGV[2])
    local wait_keys = cjson.decode(ARGV[3])

    -- Check if already claimed
    if redis.call('EXISTS', claim_key) == 1 then
        return {false, 'already_claimed'}
    end

    -- Check dependencies are completed
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

    -- Check wait_for tasks are completed
    for i, wait_key in ipairs(wait_keys) do
        local wait_data = redis.call('GET', wait_key)
        if not wait_data then
            return {false, 'missing_wait_task'}
        end
        local wait_task = cjson.decode(wait_data)
        if wait_task.status ~= 'completed' then
            return {false, 'wait_task_not_completed'}
        end
    end

    -- Atomically claim the task
    redis.call('SET', claim_key, agent_id, 'EX', 3600, 'NX')

    -- Verify we got the claim (NX means only set if not exists)
    if redis.call('GET', claim_key) ~= agent_id then
        return {false, 'claim_race_lost'}
    end

    return {true, 'claimed'}
    """

    def __init__(self, redis_client: redis.Redis, agent_id: str):
        self.redis = redis_client
        self.agent_id = agent_id
        self._claim_script = self.redis.register_script(self.CLAIM_SCRIPT)

    def _task_key(self, task_id: str) -> str:
        return f"{self.TASK_PREFIX}:{task_id}"

    def enqueue(self, task: Task) -> str:
        """Add task to the queue."""
        if not task.id:
            task.id = str(uuid.uuid4())[:8]

        task.created_by = task.created_by or self.agent_id
        task.status = TaskStatus.PENDING.value

        self.redis.set(self._task_key(task.id), json.dumps(task.to_dict()))

        score = (10 - task.priority) * 1000000 + int(datetime.utcnow().timestamp())
        self.redis.zadd(self.QUEUE_KEY, {task.id: score})

        self.redis.publish("ralph:events", json.dumps({
            'event': 'task_created',
            'task_id': task.id,
            'task_type': task.task_type,
            'created_by': task.created_by,
            'timestamp': datetime.utcnow().isoformat()
        }))

        return task.id

    def get(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        data = self.redis.get(self._task_key(task_id))
        if data:
            return Task.from_dict(json.loads(data))
        return None

    def claim(self, task: Task) -> bool:
        """Attempt to claim a task atomically with dependency checking."""
        task_key = self._task_key(task.id)
        claim_key = f"{self.CLAIMED_KEY}:{task.id}"

        dep_keys = json.dumps([self._task_key(d) for d in task.dependencies])
        wait_keys = json.dumps([self._task_key(w) for w in task.wait_for])

        result = self._claim_script(
            keys=[task_key, claim_key],
            args=[self.agent_id, dep_keys, wait_keys]
        )

        success = result[0] if result else False
        if not success:
            return False

        task.status = TaskStatus.CLAIMED.value
        task.assigned_to = self.agent_id
        task.started_at = datetime.utcnow().isoformat()
        self.redis.set(task_key, json.dumps(task.to_dict()))

        self.redis.zrem(self.QUEUE_KEY, task.id)

        self.redis.publish("ralph:events", json.dumps({
            'event': 'task_claimed',
            'task_id': task.id,
            'agent_id': self.agent_id,
            'timestamp': datetime.utcnow().isoformat()
        }))

        return True

    def _can_claim(self, task: Task) -> bool:
        """Check if task dependencies are satisfied (non-atomic, use for display only)."""
        for dep_id in task.dependencies:
            dep = self.get(dep_id)
            if not dep or dep.status != TaskStatus.COMPLETED.value:
                return False

        for wait_id in task.wait_for:
            wait_task = self.get(wait_id)
            if not wait_task or wait_task.status != TaskStatus.COMPLETED.value:
                return False

        return True

    def update_progress(self, task_id: str, status: TaskStatus, message: Optional[str] = None) -> None:
        """Update task progress."""
        task = self.get(task_id)
        if task and task.assigned_to == self.agent_id:
            task.status = status.value
            if message:
                if 'progress' not in task.metadata:
                    task.metadata['progress'] = []
                task.metadata['progress'].append({
                    'message': message,
                    'timestamp': datetime.utcnow().isoformat()
                })
            self.redis.set(self._task_key(task_id), json.dumps(task.to_dict()))

            self.redis.publish("ralph:events", json.dumps({
                'event': 'task_progress',
                'task_id': task_id,
                'status': status.value,
                'message': message,
                'agent_id': self.agent_id,
                'timestamp': datetime.utcnow().isoformat()
            }))

    def complete(self, task_id: str, result: Dict[str, Any]) -> None:
        """Mark task as complete."""
        task = self.get(task_id)
        if task and task.assigned_to == self.agent_id:
            task.status = TaskStatus.COMPLETED.value
            task.completed_at = datetime.utcnow().isoformat()
            task.result = result
            self.redis.set(self._task_key(task_id), json.dumps(task.to_dict()))

            self.redis.delete(f"{self.CLAIMED_KEY}:{task_id}")

            self.redis.publish("ralph:events", json.dumps({
                'event': 'task_completed',
                'task_id': task_id,
                'agent_id': self.agent_id,
                'result': result,
                'timestamp': datetime.utcnow().isoformat()
            }))

    def fail(self, task_id: str, error: str) -> None:
        """Mark task as failed."""
        task = self.get(task_id)
        if task and task.assigned_to == self.agent_id:
            task.status = TaskStatus.FAILED.value
            task.error = error
            task.completed_at = datetime.utcnow().isoformat()
            self.redis.set(self._task_key(task_id), json.dumps(task.to_dict()))

            self.redis.delete(f"{self.CLAIMED_KEY}:{task_id}")

            self.redis.publish("ralph:events", json.dumps({
                'event': 'task_failed',
                'task_id': task_id,
                'agent_id': self.agent_id,
                'error': error,
                'timestamp': datetime.utcnow().isoformat()
            }))

    def block(self, task_id: str, reason: str) -> None:
        """Mark task as blocked."""
        task = self.get(task_id)
        if task and task.assigned_to == self.agent_id:
            task.status = TaskStatus.BLOCKED.value
            task.metadata['blocked_reason'] = reason
            task.metadata['blocked_at'] = datetime.utcnow().isoformat()
            self.redis.set(self._task_key(task_id), json.dumps(task.to_dict()))

            self.redis.publish("ralph:events", json.dumps({
                'event': 'task_blocked',
                'task_id': task_id,
                'agent_id': self.agent_id,
                'reason': reason,
                'timestamp': datetime.utcnow().isoformat()
            }))

    def get_next(self, task_type: Optional[str] = None) -> Optional[Task]:
        """Get next available task from queue."""
        task_ids = self.redis.zrange(self.QUEUE_KEY, 0, -1)

        for task_id in task_ids:
            task = self.get(task_id)
            if not task:
                continue

            if task_type and task.task_type != task_type:
                continue

            if self.redis.exists(f"{self.CLAIMED_KEY}:{task_id}"):
                continue

            if self._can_claim(task):
                return task

        return None

    def get_pending(self, limit: int = 50) -> List[Task]:
        """Get all pending tasks."""
        task_ids = self.redis.zrange(self.QUEUE_KEY, 0, limit - 1)
        tasks = []

        for task_id in task_ids:
            task = self.get(task_id)
            if task:
                tasks.append(task)

        return tasks

    def get_by_status(self, status: TaskStatus) -> List[Task]:
        """Get all tasks with a specific status."""
        tasks = []
        for key in self.redis.scan_iter(f"{self.TASK_PREFIX}:*"):
            task = self.get(key.replace(f"{self.TASK_PREFIX}:", ""))
            if task and task.status == status.value:
                tasks.append(task)
        return tasks

    def get_artifacts(self, task_id: str) -> List[Dict]:
        """Get artifacts produced by a task."""
        task = self.get(task_id)
        if task and task.result:
            return task.result.get('artifacts', [])
        return []

    def release_claim(self, task_id: str) -> None:
        """Release claim on a task (put back in queue)."""
        task = self.get(task_id)
        if task and task.assigned_to == self.agent_id:
            task.status = TaskStatus.PENDING.value
            task.assigned_to = None
            task.started_at = None
            self.redis.set(self._task_key(task_id), json.dumps(task.to_dict()))

            self.redis.delete(f"{self.CLAIMED_KEY}:{task_id}")

            score = (10 - task.priority) * 1000000 + int(datetime.utcnow().timestamp())
            self.redis.zadd(self.QUEUE_KEY, {task_id: score})
