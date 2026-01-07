"""Agent Registry - Track active agents and their capabilities"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import redis


class AgentRegistry:
    """Manages agent registration, heartbeats, and discovery."""

    HEARTBEAT_TTL = 30
    REGISTRY_KEY = "ralph:agents"
    HEARTBEAT_KEY = "ralph:heartbeats"

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    def register(
        self,
        agent_id: str,
        agent_type: str,
        specialist_modes: List[str],
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Register agent with the registry."""
        agent_data = {
            'agent_id': agent_id,
            'agent_type': agent_type,
            'specialist_modes': specialist_modes,
            'status': 'active',
            'registered_at': datetime.utcnow().isoformat(),
            'metadata': metadata or {}
        }

        self.redis.hset(self.REGISTRY_KEY, agent_id, json.dumps(agent_data))
        self.heartbeat(agent_id)

        self.redis.publish("ralph:events", json.dumps({
            'event': 'agent_registered',
            'agent_id': agent_id,
            'agent_type': agent_type,
            'timestamp': datetime.utcnow().isoformat()
        }))

    def deregister(self, agent_id: str) -> None:
        """Remove agent from registry."""
        self.redis.hdel(self.REGISTRY_KEY, agent_id)
        self.redis.delete(f"{self.HEARTBEAT_KEY}:{agent_id}")

        self.redis.publish("ralph:events", json.dumps({
            'event': 'agent_deregistered',
            'agent_id': agent_id,
            'timestamp': datetime.utcnow().isoformat()
        }))

    def heartbeat(self, agent_id: str) -> None:
        """Update agent heartbeat timestamp."""
        self.redis.setex(
            f"{self.HEARTBEAT_KEY}:{agent_id}",
            self.HEARTBEAT_TTL,
            datetime.utcnow().isoformat()
        )

    def is_alive(self, agent_id: str) -> bool:
        """Check if agent is alive (has recent heartbeat)."""
        return self.redis.exists(f"{self.HEARTBEAT_KEY}:{agent_id}") > 0

    def get_agent(self, agent_id: str) -> Optional[Dict]:
        """Get agent info by ID."""
        data = self.redis.hget(self.REGISTRY_KEY, agent_id)
        if data:
            agent = json.loads(data)
            agent['is_alive'] = self.is_alive(agent_id)
            return agent
        return None

    def get_active_agents(self) -> List[Dict]:
        """Get all currently active agents."""
        all_agents = self.redis.hgetall(self.REGISTRY_KEY)
        active = []

        for agent_id, data in all_agents.items():
            if self.is_alive(agent_id):
                agent = json.loads(data)
                agent['is_alive'] = True
                active.append(agent)

        return active

    def get_agents_by_type(self, agent_type: str) -> List[Dict]:
        """Get all active agents of a specific type."""
        return [a for a in self.get_active_agents() if a['agent_type'] == agent_type]

    def get_agents_with_mode(self, mode: str) -> List[Dict]:
        """Get all active agents that support a specialist mode."""
        return [
            a for a in self.get_active_agents()
            if mode in a.get('specialist_modes', [])
        ]

    def update_status(self, agent_id: str, status: str, details: Optional[str] = None) -> None:
        """Update agent status (active, busy, blocked, etc)."""
        data = self.redis.hget(self.REGISTRY_KEY, agent_id)
        if data:
            agent = json.loads(data)
            agent['status'] = status
            agent['status_updated_at'] = datetime.utcnow().isoformat()
            if details:
                agent['status_details'] = details
            self.redis.hset(self.REGISTRY_KEY, agent_id, json.dumps(agent))

            self.redis.publish("ralph:events", json.dumps({
                'event': 'agent_status_changed',
                'agent_id': agent_id,
                'status': status,
                'details': details,
                'timestamp': datetime.utcnow().isoformat()
            }))

    def cleanup_stale(self) -> List[str]:
        """Remove agents without recent heartbeat."""
        all_agents = self.redis.hgetall(self.REGISTRY_KEY)
        removed = []

        for agent_id in all_agents.keys():
            if not self.is_alive(agent_id):
                self.deregister(agent_id)
                removed.append(agent_id)

        return removed
