"""Main Ralph Agent Client - Central coordination hub"""

import os
import json
import time
import threading
from typing import Optional, Dict, Any, Callable
from datetime import datetime

import redis

from .registry import AgentRegistry
from .locks import FileLock
from .tasks import TaskQueue, Task


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

        self.redis = redis.from_url(self.redis_url, decode_responses=True)
        self.registry = AgentRegistry(self.redis)
        self.task_queue = TaskQueue(self.redis, self.agent_id)
        self.file_lock = FileLock(self.redis, self.agent_id)

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
                time.sleep(10)
            except Exception as e:
                print(f"Heartbeat error: {e}")
                time.sleep(5)

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

    def claim_task(self, task: Task) -> bool:
        """Attempt to claim a task from the queue."""
        return self.task_queue.claim(task)

    def complete_task(self, task_id: str, result: Dict[str, Any]) -> None:
        """Mark task as complete with result."""
        self.task_queue.complete(task_id, result)

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
