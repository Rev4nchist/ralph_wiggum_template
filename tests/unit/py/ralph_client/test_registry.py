"""P0 Critical Tests: Heartbeat and Agent Discovery.

Tests the AgentRegistry class which manages:
- Agent registration with metadata
- Heartbeat updates (TTL-based liveness)
- Agent discovery and filtering
- Stale agent cleanup
"""

import json
import time
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "lib" / "ralph-client"))

from registry import AgentRegistry


class TestAgentRegistration:
    """P0 Critical: Agent registration and deregistration."""

    @pytest.fixture
    def registry(self, mock_redis):
        return AgentRegistry(mock_redis)

    @pytest.fixture
    def agent_id(self):
        return "test-agent-001"

    @pytest.mark.p0
    def test_register_stores_agent_data(self, registry, mock_redis, agent_id):
        """Register stores agent metadata in hash."""
        registry.register(agent_id, "backend", ["implement", "debug"])

        stored = mock_redis.hget("ralph:agents", agent_id)
        assert stored is not None
        data = json.loads(stored)
        assert data["agent_id"] == agent_id
        assert data["agent_type"] == "backend"
        assert "implement" in data["specialist_modes"]

    @pytest.mark.p0
    def test_register_creates_heartbeat(self, registry, mock_redis, agent_id):
        """Register creates heartbeat key with TTL."""
        registry.register(agent_id, "backend", ["implement"])

        assert mock_redis.exists(f"ralph:heartbeats:{agent_id}")
        ttl = mock_redis.ttl(f"ralph:heartbeats:{agent_id}")
        assert ttl > 0

    @pytest.mark.p0
    def test_deregister_removes_agent(self, registry, mock_redis, agent_id):
        """Deregister removes agent from registry."""
        registry.register(agent_id, "frontend", ["implement"])

        registry.deregister(agent_id)

        assert mock_redis.hget("ralph:agents", agent_id) is None
        assert not mock_redis.exists(f"ralph:heartbeats:{agent_id}")


class TestHeartbeat:
    """P0 Critical: Heartbeat TTL-based liveness detection."""

    @pytest.fixture
    def registry(self, mock_redis):
        return AgentRegistry(mock_redis)

    @pytest.fixture
    def agent_id(self):
        return "heartbeat-agent-001"

    @pytest.mark.p0
    def test_heartbeat_updates_ttl(self, registry, mock_redis, agent_id):
        """Heartbeat refreshes TTL on heartbeat key."""
        registry.register(agent_id, "frontend", ["implement"])

        time.sleep(1.5)
        old_ttl = mock_redis.ttl(f"ralph:heartbeats:{agent_id}")

        registry.heartbeat(agent_id)

        new_ttl = mock_redis.ttl(f"ralph:heartbeats:{agent_id}")
        assert new_ttl > old_ttl, "Heartbeat should refresh TTL"

    @pytest.mark.p0
    def test_is_alive_returns_true_with_heartbeat(self, registry, mock_redis, agent_id):
        """is_alive returns True when heartbeat exists."""
        registry.register(agent_id, "backend", ["debug"])

        assert registry.is_alive(agent_id) is True

    @pytest.mark.p0
    def test_is_alive_returns_false_without_heartbeat(self, registry, mock_redis, agent_id):
        """is_alive returns False when heartbeat expired."""
        registry.register(agent_id, "backend", ["debug"])
        mock_redis.delete(f"ralph:heartbeats:{agent_id}")

        assert registry.is_alive(agent_id) is False


class TestAgentDiscovery:
    """P1 High: Agent discovery and filtering."""

    @pytest.fixture
    def registry(self, mock_redis):
        return AgentRegistry(mock_redis)

    @pytest.fixture
    def backend_agent_id(self):
        return "backend-agent-001"

    @pytest.fixture
    def frontend_agent_id(self):
        return "frontend-agent-001"

    @pytest.mark.p1
    def test_get_active_agents_returns_alive_only(self, registry, mock_redis, backend_agent_id, frontend_agent_id):
        """get_active_agents only returns agents with valid heartbeat."""
        registry.register(backend_agent_id, "backend", ["implement", "debug"])
        registry.register(frontend_agent_id, "frontend", ["implement", "review"])
        mock_redis.delete(f"ralph:heartbeats:{frontend_agent_id}")

        active = registry.get_active_agents()

        active_ids = [a["agent_id"] for a in active]
        assert backend_agent_id in active_ids
        assert frontend_agent_id not in active_ids

    @pytest.mark.p1
    def test_get_agents_by_type(self, registry, mock_redis, backend_agent_id, frontend_agent_id):
        """get_agents_by_type filters by agent type."""
        registry.register(backend_agent_id, "backend", ["implement"])
        registry.register(frontend_agent_id, "frontend", ["implement"])

        backends = registry.get_agents_by_type("backend")
        frontends = registry.get_agents_by_type("frontend")

        assert len(backends) == 1
        assert backends[0]["agent_id"] == backend_agent_id
        assert len(frontends) == 1
        assert frontends[0]["agent_id"] == frontend_agent_id

    @pytest.mark.p1
    def test_get_agents_with_mode(self, registry, mock_redis, backend_agent_id, frontend_agent_id):
        """get_agents_with_mode filters by capability."""
        registry.register(backend_agent_id, "backend", ["implement", "debug"])
        registry.register(frontend_agent_id, "frontend", ["implement", "review"])

        debuggers = registry.get_agents_with_mode("debug")
        reviewers = registry.get_agents_with_mode("review")

        assert len(debuggers) == 1
        assert debuggers[0]["agent_id"] == backend_agent_id
        assert len(reviewers) == 1
        assert reviewers[0]["agent_id"] == frontend_agent_id


class TestStaleAgentCleanup:
    """P1 High: Cleanup of stale/dead agents."""

    @pytest.fixture
    def registry(self, mock_redis):
        return AgentRegistry(mock_redis)

    @pytest.fixture
    def agent_id(self):
        return "cleanup-agent-001"

    @pytest.mark.p1
    def test_cleanup_stale_removes_dead_agents(self, registry, mock_redis, agent_id):
        """cleanup_stale removes agents without heartbeat."""
        registry.register(agent_id, "integration", ["implement"])
        dead_agent_data = json.dumps({
            "agent_id": "dead-agent",
            "agent_type": "backend",
            "specialist_modes": ["implement"],
            "status": "active"
        })
        mock_redis.hset("ralph:agents", "dead-agent", dead_agent_data)

        removed = registry.cleanup_stale()

        assert "dead-agent" in removed
        assert mock_redis.hget("ralph:agents", "dead-agent") is None
        assert mock_redis.hget("ralph:agents", agent_id) is not None

    @pytest.mark.p1
    def test_get_agent_includes_alive_status(self, registry, mock_redis, agent_id):
        """get_agent includes is_alive field."""
        registry.register(agent_id, "backend", ["implement"])

        agent = registry.get_agent(agent_id)

        assert agent is not None
        assert agent["is_alive"] is True

    @pytest.mark.p1
    def test_update_status_changes_agent_status(self, registry, mock_redis, agent_id):
        """update_status modifies agent status field."""
        registry.register(agent_id, "backend", ["implement"])

        registry.update_status(agent_id, "busy", "processing task")

        agent = registry.get_agent(agent_id)
        assert agent["status"] == "busy"
