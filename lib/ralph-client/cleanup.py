"""Orphan task cleanup for crashed agents."""
import json
import time
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class OrphanedTask:
    task_id: str
    agent_id: str
    claimed_at: float


class OrphanCleaner:
    """Cleans up tasks left orphaned by crashed agents."""

    def __init__(self, redis_client):
        self.redis = redis_client
        self.orphan_threshold_seconds = 300  # 5 minutes

    def cleanup_orphaned_claims(self) -> List[str]:
        """Find and release tasks claimed by dead agents."""
        released = []

        # Scan for all claimed tasks
        for key in self.redis.scan_iter('ralph:tasks:claimed:*'):
            task_id = key.decode() if isinstance(key, bytes) else key
            task_id = task_id.split(':')[-1]

            agent_id = self.redis.get(f'ralph:tasks:claimed:{task_id}')
            if agent_id:
                agent_id = agent_id.decode() if isinstance(agent_id, bytes) else agent_id

                # Check if agent is alive via heartbeat
                heartbeat_key = f'ralph:heartbeats:{agent_id}'
                if not self.redis.exists(heartbeat_key):
                    self._release_orphan(task_id, agent_id)
                    released.append(task_id)

        return released

    def _release_orphan(self, task_id: str, agent_id: str):
        """Reset orphaned task to PENDING and re-add to queue."""
        task_key = f'ralph:tasks:data:{task_id}'
        claim_key = f'ralph:tasks:claimed:{task_id}'
        queue_key = 'ralph:tasks:queue'

        # Get task data
        task_data = self.redis.get(task_key)
        if task_data:
            task = json.loads(task_data)
            task['status'] = 'pending'
            task['assigned_to'] = None
            task['started_at'] = None
            task['orphan_recovered'] = True
            task['recovered_from_agent'] = agent_id
            task['recovered_at'] = time.time()

            # Update task
            self.redis.set(task_key, json.dumps(task))

            # Delete claim
            self.redis.delete(claim_key)

            # Re-add to queue with original priority
            priority = task.get('priority', 5)
            self.redis.zadd(queue_key, {task_id: priority})

    def get_orphaned_tasks(self) -> List[OrphanedTask]:
        """List all currently orphaned tasks without releasing them."""
        orphans = []

        for key in self.redis.scan_iter('ralph:tasks:claimed:*'):
            task_id = key.decode() if isinstance(key, bytes) else key
            task_id = task_id.split(':')[-1]

            agent_id = self.redis.get(f'ralph:tasks:claimed:{task_id}')
            if agent_id:
                agent_id = agent_id.decode() if isinstance(agent_id, bytes) else agent_id

                if not self.redis.exists(f'ralph:heartbeats:{agent_id}'):
                    # Get claimed_at from task data
                    task_data = self.redis.get(f'ralph:tasks:data:{task_id}')
                    claimed_at = 0.0
                    if task_data:
                        task = json.loads(task_data)
                        claimed_at = task.get('started_at', 0.0) or 0.0

                    orphans.append(OrphanedTask(
                        task_id=task_id,
                        agent_id=agent_id,
                        claimed_at=claimed_at
                    ))

        return orphans
