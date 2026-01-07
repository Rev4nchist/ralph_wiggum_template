"""File Locking - Pessimistic locking for collaborative editing"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Set

import redis


class FileLock:
    """Distributed file locking for multi-agent collaboration.

    Uses pessimistic locking strategy:
    - Agent must acquire lock before editing
    - Lock has TTL to prevent deadlocks
    - Owner can extend lock if still working
    """

    LOCK_PREFIX = "ralph:locks:file"
    DEFAULT_TTL = 300

    def __init__(self, redis_client: redis.Redis, agent_id: str):
        self.redis = redis_client
        self.agent_id = agent_id
        self._held_locks: Set[str] = set()

    def _lock_key(self, file_path: str) -> str:
        """Generate Redis key for file lock."""
        safe_path = file_path.replace('/', ':').replace('\\', ':')
        return f"{self.LOCK_PREFIX}:{safe_path}"

    def acquire(self, file_path: str, ttl: int = DEFAULT_TTL) -> bool:
        """Attempt to acquire lock on a file.

        Returns True if lock acquired, False if file is locked by another agent.
        """
        key = self._lock_key(file_path)

        lock_data = json.dumps({
            'agent_id': self.agent_id,
            'file_path': file_path,
            'acquired_at': datetime.utcnow().isoformat(),
            'ttl': ttl
        })

        acquired = self.redis.set(key, lock_data, nx=True, ex=ttl)

        if acquired:
            self._held_locks.add(file_path)
            self.redis.publish("ralph:events", json.dumps({
                'event': 'file_locked',
                'agent_id': self.agent_id,
                'file_path': file_path,
                'timestamp': datetime.utcnow().isoformat()
            }))
            return True

        existing = self.redis.get(key)
        if existing:
            data = json.loads(existing)
            if data['agent_id'] == self.agent_id:
                self.extend(file_path, ttl)
                return True

        return False

    def release(self, file_path: str) -> bool:
        """Release lock on a file."""
        key = self._lock_key(file_path)

        existing = self.redis.get(key)
        if existing:
            data = json.loads(existing)
            if data['agent_id'] == self.agent_id:
                self.redis.delete(key)
                self._held_locks.discard(file_path)

                self.redis.publish("ralph:events", json.dumps({
                    'event': 'file_unlocked',
                    'agent_id': self.agent_id,
                    'file_path': file_path,
                    'timestamp': datetime.utcnow().isoformat()
                }))
                return True

        return False

    def release_all(self) -> int:
        """Release all locks held by this agent."""
        released = 0
        for file_path in list(self._held_locks):
            if self.release(file_path):
                released += 1
        return released

    def extend(self, file_path: str, ttl: int = DEFAULT_TTL) -> bool:
        """Extend TTL on a lock we own."""
        key = self._lock_key(file_path)

        existing = self.redis.get(key)
        if existing:
            data = json.loads(existing)
            if data['agent_id'] == self.agent_id:
                self.redis.expire(key, ttl)
                return True

        return False

    def is_locked(self, file_path: str) -> bool:
        """Check if file is currently locked."""
        return self.redis.exists(self._lock_key(file_path)) > 0

    def get_lock_info(self, file_path: str) -> Optional[Dict]:
        """Get information about current lock holder."""
        data = self.redis.get(self._lock_key(file_path))
        if data:
            return json.loads(data)
        return None

    def get_lock_owner(self, file_path: str) -> Optional[str]:
        """Get agent ID of current lock holder."""
        info = self.get_lock_info(file_path)
        return info['agent_id'] if info else None

    def is_owned_by_me(self, file_path: str) -> bool:
        """Check if we own the lock on this file."""
        owner = self.get_lock_owner(file_path)
        return owner == self.agent_id

    def get_all_locks(self) -> List[Dict]:
        """Get all currently held file locks."""
        pattern = f"{self.LOCK_PREFIX}:*"
        locks = []

        for key in self.redis.scan_iter(pattern):
            data = self.redis.get(key)
            if data:
                lock_info = json.loads(data)
                ttl = self.redis.ttl(key)
                lock_info['remaining_ttl'] = ttl
                locks.append(lock_info)

        return locks

    def get_my_locks(self) -> List[Dict]:
        """Get all locks held by this agent."""
        return [lock for lock in self.get_all_locks() if lock['agent_id'] == self.agent_id]

    def wait_for_lock(self, file_path: str, timeout: int = 60, poll_interval: float = 1.0) -> bool:
        """Wait until lock is available, then acquire it."""
        import time

        start = time.time()
        while time.time() - start < timeout:
            if self.acquire(file_path):
                return True
            time.sleep(poll_interval)

        return False

    def force_release(self, file_path: str) -> bool:
        """Force release a lock (admin operation). Use with caution."""
        key = self._lock_key(file_path)

        if self.redis.exists(key):
            lock_info = self.get_lock_info(file_path)
            self.redis.delete(key)

            self.redis.publish("ralph:events", json.dumps({
                'event': 'file_force_unlocked',
                'agent_id': self.agent_id,
                'previous_owner': lock_info.get('agent_id') if lock_info else None,
                'file_path': file_path,
                'timestamp': datetime.utcnow().isoformat()
            }))
            return True

        return False
