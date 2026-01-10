"""Main Ralph Agent Client - Central coordination hub"""

import os
import sys
import json
import time
import random
import threading
from typing import Optional, Dict, Any, Callable, List
from datetime import datetime

import redis
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError


class RedisStartupError(Exception):
    """Failed to connect to Redis after all retries."""
    pass


def create_redis_client(
    redis_url: str,
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 30.0
) -> redis.Redis:
    """Create Redis client with exponential backoff retry.

    Args:
        redis_url: Redis connection URL
        max_retries: Maximum connection attempts (default 5)
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay cap in seconds

    Returns:
        Connected Redis client

    Raises:
        RedisStartupError: If connection fails after all retries
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            client = redis.from_url(redis_url, decode_responses=True)
            client.ping()
            return client
        except (RedisConnectionError, RedisTimeoutError, OSError) as e:
            last_error = e
            delay = min(base_delay * (2 ** attempt), max_delay)
            jitter = delay * 0.25 * (2 * random.random() - 1)
            actual_delay = delay + jitter

            print(
                f"Redis connection failed (attempt {attempt + 1}/{max_retries}): {e}",
                file=sys.stderr
            )

            if attempt < max_retries - 1:
                print(f"Retrying in {actual_delay:.1f}s...", file=sys.stderr)
                time.sleep(actual_delay)

    raise RedisStartupError(
        f"Failed to connect to Redis at {redis_url} after {max_retries} attempts: {last_error}"
    )

from .registry import AgentRegistry
from .locks import FileLock
from .tasks import TaskQueue, Task

# Import memory system
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from memory.project_memory import ProjectMemory


class RalphClient:
    """Main client for Ralph multi-agent coordination.

    Handles:
    - Agent registration and heartbeat
    - Task queue operations
    - File locking for collaboration
    - Inter-agent messaging
    - Telegram notifications
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        redis_url: Optional[str] = None
    ):
        self.agent_id = agent_id or os.environ.get('RALPH_AGENT_ID', 'agent-default')
        self.agent_type = agent_type or os.environ.get('RALPH_AGENT_TYPE', 'general')
        self.redis_url = redis_url or os.environ.get('REDIS_URL', 'redis://localhost:6379')

        self.redis = create_redis_client(self.redis_url)
        self.registry = AgentRegistry(self.redis)
        self.task_queue = TaskQueue(self.redis, self.agent_id)
        self.file_lock = FileLock(self.redis, self.agent_id)

        self.project_id = os.environ.get('RALPH_PROJECT_ID', 'default')
        self.memory = ProjectMemory(
            project_id=self.project_id,
            agent_id=self.agent_id,
            redis_client=self.redis
        )

        self._heartbeat_thread: Optional[threading.Thread] = None
        self._running = False
        self._message_handlers: Dict[str, Callable] = {}

    def start(self) -> None:
        """Start the agent - register and begin heartbeat."""
        specialist_modes = os.environ.get('RALPH_SPECIALIST_MODES', 'implement').split(',')

        self.registry.register(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            specialist_modes=specialist_modes,
            metadata={
                'started_at': datetime.utcnow().isoformat(),
                'workspace': os.getcwd()
            }
        )

        self._running = True
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

        self._subscribe_to_messages()

    def stop(self) -> None:
        """Stop the agent - deregister and cleanup."""
        self._running = False
        self.registry.deregister(self.agent_id)
        self.file_lock.release_all()

        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=2)

    def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat to indicate agent is alive."""
        while self._running:
            try:
                self.registry.heartbeat(self.agent_id)
                time.sleep(5)
            except Exception as e:
                print(f"Heartbeat error: {e}")
                time.sleep(2)

    def _subscribe_to_messages(self) -> None:
        """Subscribe to agent-specific message channel."""
        pubsub = self.redis.pubsub()
        pubsub.subscribe(f"ralph:messages:{self.agent_id}")
        pubsub.subscribe("ralph:broadcast")

        def listen():
            for message in pubsub.listen():
                if message['type'] == 'message':
                    self._handle_message(message)

        thread = threading.Thread(target=listen, daemon=True)
        thread.start()

    def _handle_message(self, message: Dict) -> None:
        """Process incoming message."""
        try:
            data = json.loads(message['data'])
            msg_type = data.get('type', 'unknown')

            if msg_type in self._message_handlers:
                self._message_handlers[msg_type](data)
            else:
                print(f"Unhandled message type: {msg_type}")
        except json.JSONDecodeError:
            print(f"Invalid message format: {message['data']}")

    def on_message(self, msg_type: str) -> Callable:
        """Decorator to register message handlers."""
        def decorator(func: Callable) -> Callable:
            self._message_handlers[msg_type] = func
            return func
        return decorator

    def send_message(self, target_agent: str, msg_type: str, payload: Dict[str, Any]) -> None:
        """Send message to another agent."""
        message = {
            'type': msg_type,
            'from': self.agent_id,
            'timestamp': datetime.utcnow().isoformat(),
            'payload': payload
        }
        self.redis.publish(f"ralph:messages:{target_agent}", json.dumps(message))

    def broadcast(self, msg_type: str, payload: Dict[str, Any]) -> None:
        """Broadcast message to all agents."""
        message = {
            'type': msg_type,
            'from': self.agent_id,
            'timestamp': datetime.utcnow().isoformat(),
            'payload': payload
        }
        self.redis.publish("ralph:broadcast", json.dumps(message))

    def get_active_agents(self) -> list:
        """Get list of currently active agents."""
        return self.registry.get_active_agents()

    def claim_task(self, task: Task) -> Dict[str, Any]:
        """Attempt to claim a task from the queue with memory context."""
        claimed = self.task_queue.claim(task)
        if not claimed:
            return {'claimed': False, 'task': None, 'context': None, 'memories': []}

        task_context = self.memory.get_task_context(task.id) if hasattr(task, 'id') else {}
        task_desc = getattr(task, 'description', '') or getattr(task, 'title', '')
        relevant_memories = self.memory.recall(task_desc, limit=5) if task_desc else []

        return {
            'claimed': True,
            'task': task,
            'context': task_context,
            'memories': relevant_memories
        }

    def complete_task(
        self,
        task_id: str,
        result: Dict[str, Any],
        summary: str = "",
        learnings: Optional[List[str]] = None,
        next_steps: Optional[List[str]] = None
    ) -> None:
        """Mark task as complete with result and commit learnings to memory."""
        self.task_queue.complete(task_id, result)

        if summary:
            self.memory.commit_task(
                task_id=task_id,
                summary=summary,
                learnings=learnings or []
            )

        if next_steps:
            self.memory.handoff(
                task_id=task_id,
                summary=summary or f"Task {task_id} completed",
                next_steps=next_steps
            )

    def fail_task(self, task_id: str, error: str) -> None:
        """Mark task as failed."""
        self.task_queue.fail(task_id, error)

    def acquire_file_lock(self, file_path: str, timeout: int = 300) -> bool:
        """Acquire lock on a file for exclusive editing."""
        return self.file_lock.acquire(file_path, timeout)

    def release_file_lock(self, file_path: str) -> None:
        """Release lock on a file."""
        self.file_lock.release(file_path)

    def notify_telegram(self, message: str, level: str = "info") -> None:
        """Send notification via Telegram with agent context."""
        formatted = f"[{self.agent_id}] {message}"

        self.redis.rpush("ralph:telegram:queue", json.dumps({
            'agent_id': self.agent_id,
            'message': formatted,
            'level': level,
            'timestamp': datetime.utcnow().isoformat()
        }))

    def get_telegram_response(self, timeout: int = 30) -> Optional[str]:
        """Retrieve response from Telegram question notification.

        Args:
            timeout: Maximum seconds to wait for response

        Returns:
            Response text if received, None if timeout
        """
        key = f"ralph:telegram:response:{self.agent_id}"
        for _ in range(timeout):
            response = self.redis.get(key)
            if response:
                self.redis.delete(key)
                return response
            time.sleep(1)
        return None

    def log_progress(self, task_id: str, message: str) -> None:
        """Log progress for a task."""
        self.redis.rpush(f"ralph:progress:{task_id}", json.dumps({
            'agent_id': self.agent_id,
            'message': message,
            'timestamp': datetime.utcnow().isoformat()
        }))

    def store_artifact(self, name: str, data: Any, task_id: Optional[str] = None) -> str:
        """Store an artifact (build output, test results, etc)."""
        artifact_id = f"{self.agent_id}:{name}:{int(time.time())}"

        self.redis.hset(f"ralph:artifacts:{artifact_id}", mapping={
            'name': name,
            'agent_id': self.agent_id,
            'task_id': task_id or '',
            'data': json.dumps(data) if not isinstance(data, str) else data,
            'created_at': datetime.utcnow().isoformat()
        })

        self.redis.expire(f"ralph:artifacts:{artifact_id}", 86400)

        return artifact_id

    def get_artifact(self, artifact_id: str) -> Optional[Dict]:
        """Retrieve an artifact by ID."""
        data = self.redis.hgetall(f"ralph:artifacts:{artifact_id}")
        if data:
            if 'data' in data:
                try:
                    data['data'] = json.loads(data['data'])
                except json.JSONDecodeError:
                    pass
            return data
        return None

    def remember(
        self,
        content: str,
        category: str = "general",
        tags: Optional[List[str]] = None,
        task_id: Optional[str] = None
    ) -> str:
        """Store a memory for future recall."""
        return self.memory.remember(
            content=content,
            category=category,
            tags=tags or [],
            task_id=task_id
        )

    def recall(
        self,
        query: str,
        category: Optional[str] = None,
        task_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """Search memories by query."""
        return self.memory.recall(
            query=query,
            category=category,
            task_id=task_id,
            limit=limit
        )

    def get_project_context(self) -> Dict[str, Any]:
        """Get accumulated project context."""
        return self.memory.get_project_context()

    def note_architecture(self, decision: str, rationale: str = "") -> str:
        """Record an architecture decision."""
        return self.memory.note_architecture(decision, rationale)

    def note_pattern(self, pattern: str, example: str = "") -> str:
        """Record a discovered pattern."""
        return self.memory.note_pattern(pattern, example)

    def note_blocker(self, blocker: str, resolution: str = "") -> str:
        """Record a blocker and its resolution."""
        return self.memory.note_blocker(blocker, resolution)
