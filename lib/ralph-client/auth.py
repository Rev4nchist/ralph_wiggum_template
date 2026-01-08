"""Authentication layer for Ralph agents."""
import secrets
import json
import hashlib
from enum import Enum
from typing import Optional
from dataclasses import dataclass


class AuthLevel(Enum):
    READONLY = 'readonly'
    AGENT = 'agent'
    ADMIN = 'admin'


class AuthError(Exception):
    """Authentication error."""
    pass


@dataclass
class AgentCredentials:
    agent_id: str
    token: str
    level: AuthLevel


class TokenAuth:
    """Token-based authentication for agents."""

    TOKEN_KEY = "ralph:tokens"
    TOKEN_LENGTH = 32

    def __init__(self, redis_client):
        self.redis = redis_client

    def register_agent(self, agent_id: str, level: AuthLevel = AuthLevel.AGENT) -> str:
        """Register a new agent and return its token."""
        token = secrets.token_hex(self.TOKEN_LENGTH)

        token_hash = self._hash_token(token)

        credentials = {
            'token_hash': token_hash,
            'level': level.value,
            'created_at': __import__('time').time()
        }

        self.redis.hset(self.TOKEN_KEY, agent_id, json.dumps(credentials))

        return token

    def verify(self, agent_id: str, token: str) -> AuthLevel:
        """Verify agent token and return auth level."""
        stored = self.redis.hget(self.TOKEN_KEY, agent_id)

        if not stored:
            raise AuthError(f'Unknown agent: {agent_id}')

        stored = stored.decode() if isinstance(stored, bytes) else stored
        data = json.loads(stored)

        token_hash = self._hash_token(token)
        if not secrets.compare_digest(data['token_hash'], token_hash):
            raise AuthError('Invalid token')

        return AuthLevel(data['level'])

    def revoke(self, agent_id: str) -> bool:
        """Revoke an agent's token."""
        return self.redis.hdel(self.TOKEN_KEY, agent_id) > 0

    def update_level(self, agent_id: str, new_level: AuthLevel) -> bool:
        """Update an agent's authorization level."""
        stored = self.redis.hget(self.TOKEN_KEY, agent_id)

        if not stored:
            return False

        stored = stored.decode() if isinstance(stored, bytes) else stored
        data = json.loads(stored)
        data['level'] = new_level.value

        self.redis.hset(self.TOKEN_KEY, agent_id, json.dumps(data))
        return True

    def list_agents(self) -> dict:
        """List all registered agents (without tokens)."""
        agents = {}
        all_data = self.redis.hgetall(self.TOKEN_KEY)

        for agent_id, creds in all_data.items():
            agent_id = agent_id.decode() if isinstance(agent_id, bytes) else agent_id
            creds = creds.decode() if isinstance(creds, bytes) else creds
            data = json.loads(creds)

            agents[agent_id] = {
                'level': data['level'],
                'created_at': data.get('created_at')
            }

        return agents

    def _hash_token(self, token: str) -> str:
        """Hash a token using SHA-256."""
        return hashlib.sha256(token.encode()).hexdigest()

    def check_permission(self, agent_id: str, token: str, required_level: AuthLevel) -> bool:
        """Check if agent has required permission level."""
        try:
            level = self.verify(agent_id, token)

            if level == AuthLevel.ADMIN:
                return True

            if level == AuthLevel.AGENT and required_level in (AuthLevel.AGENT, AuthLevel.READONLY):
                return True

            if level == AuthLevel.READONLY and required_level == AuthLevel.READONLY:
                return True

            return False

        except AuthError:
            return False


def require_auth(required_level: AuthLevel = AuthLevel.AGENT):
    """Decorator to require authentication on methods."""
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            agent_id = getattr(self, 'agent_id', None) or kwargs.get('agent_id')
            token = getattr(self, '_auth_token', None) or kwargs.get('token')

            if not agent_id or not token:
                raise AuthError('Authentication required')

            auth = getattr(self, '_auth', None)
            if not auth:
                raise AuthError('Auth not configured')

            if not auth.check_permission(agent_id, token, required_level):
                raise AuthError(f'Insufficient permissions. Required: {required_level.value}')

            return func(self, *args, **kwargs)
        return wrapper
    return decorator
