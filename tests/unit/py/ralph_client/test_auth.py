"""Unit tests for Ralph authentication module."""

import pytest
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "lib" / "ralph-client"))

from auth import TokenAuth, AuthLevel, AuthError, AgentCredentials, require_auth


class TestAuthLevel:
    """Tests for AuthLevel enum."""

    def test_auth_levels_have_correct_values(self):
        assert AuthLevel.READONLY.value == 'readonly'
        assert AuthLevel.AGENT.value == 'agent'
        assert AuthLevel.ADMIN.value == 'admin'

    def test_auth_level_from_value(self):
        assert AuthLevel('readonly') == AuthLevel.READONLY
        assert AuthLevel('agent') == AuthLevel.AGENT
        assert AuthLevel('admin') == AuthLevel.ADMIN


class TestAgentCredentials:
    """Tests for AgentCredentials dataclass."""

    def test_creates_credentials(self):
        creds = AgentCredentials(
            agent_id='test-agent',
            token='secret-token',
            level=AuthLevel.AGENT
        )
        assert creds.agent_id == 'test-agent'
        assert creds.token == 'secret-token'
        assert creds.level == AuthLevel.AGENT


class TestTokenAuth:
    """Tests for TokenAuth class."""

    def test_register_agent_returns_token(self, mock_redis):
        auth = TokenAuth(mock_redis)
        token = auth.register_agent('agent-001')

        assert token is not None
        assert len(token) == 64  # 32 bytes hex = 64 chars

    def test_register_agent_stores_hashed_token(self, mock_redis):
        auth = TokenAuth(mock_redis)
        token = auth.register_agent('agent-001')

        stored = mock_redis.hget(TokenAuth.TOKEN_KEY, 'agent-001')
        data = json.loads(stored)

        assert 'token_hash' in data
        assert data['token_hash'] != token  # Should be hashed, not plain
        assert data['level'] == 'agent'

    def test_register_agent_with_custom_level(self, mock_redis):
        auth = TokenAuth(mock_redis)
        auth.register_agent('admin-agent', AuthLevel.ADMIN)

        stored = mock_redis.hget(TokenAuth.TOKEN_KEY, 'admin-agent')
        data = json.loads(stored)

        assert data['level'] == 'admin'

    def test_verify_valid_token(self, mock_redis):
        auth = TokenAuth(mock_redis)
        token = auth.register_agent('agent-001')

        level = auth.verify('agent-001', token)
        assert level == AuthLevel.AGENT

    def test_verify_invalid_token_raises(self, mock_redis):
        auth = TokenAuth(mock_redis)
        auth.register_agent('agent-001')

        with pytest.raises(AuthError, match='Invalid token'):
            auth.verify('agent-001', 'wrong-token')

    def test_verify_unknown_agent_raises(self, mock_redis):
        auth = TokenAuth(mock_redis)

        with pytest.raises(AuthError, match='Unknown agent'):
            auth.verify('nonexistent', 'any-token')

    def test_revoke_removes_agent(self, mock_redis):
        auth = TokenAuth(mock_redis)
        token = auth.register_agent('agent-001')

        result = auth.revoke('agent-001')
        assert result is True

        with pytest.raises(AuthError, match='Unknown agent'):
            auth.verify('agent-001', token)

    def test_revoke_nonexistent_returns_false(self, mock_redis):
        auth = TokenAuth(mock_redis)
        result = auth.revoke('nonexistent')
        assert result is False

    def test_update_level(self, mock_redis):
        auth = TokenAuth(mock_redis)
        token = auth.register_agent('agent-001', AuthLevel.READONLY)

        result = auth.update_level('agent-001', AuthLevel.ADMIN)
        assert result is True

        level = auth.verify('agent-001', token)
        assert level == AuthLevel.ADMIN

    def test_update_level_nonexistent_returns_false(self, mock_redis):
        auth = TokenAuth(mock_redis)
        result = auth.update_level('nonexistent', AuthLevel.ADMIN)
        assert result is False

    def test_list_agents(self, mock_redis):
        auth = TokenAuth(mock_redis)
        auth.register_agent('agent-001', AuthLevel.AGENT)
        auth.register_agent('agent-002', AuthLevel.ADMIN)
        auth.register_agent('agent-003', AuthLevel.READONLY)

        agents = auth.list_agents()

        assert len(agents) == 3
        assert 'agent-001' in agents
        assert agents['agent-001']['level'] == 'agent'
        assert agents['agent-002']['level'] == 'admin'
        assert agents['agent-003']['level'] == 'readonly'

    def test_list_agents_excludes_tokens(self, mock_redis):
        auth = TokenAuth(mock_redis)
        auth.register_agent('agent-001')

        agents = auth.list_agents()

        assert 'token' not in agents['agent-001']
        assert 'token_hash' not in agents['agent-001']


class TestCheckPermission:
    """Tests for permission checking."""

    def test_admin_can_do_everything(self, mock_redis):
        auth = TokenAuth(mock_redis)
        token = auth.register_agent('admin', AuthLevel.ADMIN)

        assert auth.check_permission('admin', token, AuthLevel.ADMIN) is True
        assert auth.check_permission('admin', token, AuthLevel.AGENT) is True
        assert auth.check_permission('admin', token, AuthLevel.READONLY) is True

    def test_agent_can_do_agent_and_readonly(self, mock_redis):
        auth = TokenAuth(mock_redis)
        token = auth.register_agent('agent', AuthLevel.AGENT)

        assert auth.check_permission('agent', token, AuthLevel.ADMIN) is False
        assert auth.check_permission('agent', token, AuthLevel.AGENT) is True
        assert auth.check_permission('agent', token, AuthLevel.READONLY) is True

    def test_readonly_can_only_read(self, mock_redis):
        auth = TokenAuth(mock_redis)
        token = auth.register_agent('reader', AuthLevel.READONLY)

        assert auth.check_permission('reader', token, AuthLevel.ADMIN) is False
        assert auth.check_permission('reader', token, AuthLevel.AGENT) is False
        assert auth.check_permission('reader', token, AuthLevel.READONLY) is True

    def test_invalid_token_returns_false(self, mock_redis):
        auth = TokenAuth(mock_redis)
        auth.register_agent('agent')

        assert auth.check_permission('agent', 'wrong-token', AuthLevel.READONLY) is False

    def test_unknown_agent_returns_false(self, mock_redis):
        auth = TokenAuth(mock_redis)

        assert auth.check_permission('unknown', 'any-token', AuthLevel.READONLY) is False


class TestRequireAuthDecorator:
    """Tests for the require_auth decorator."""

    def test_decorator_blocks_without_auth(self, mock_redis):
        auth = TokenAuth(mock_redis)

        class TestService:
            def __init__(self):
                self.agent_id = None
                self._auth_token = None
                self._auth = auth

            @require_auth()
            def protected_method(self):
                return 'success'

        service = TestService()

        with pytest.raises(AuthError, match='Authentication required'):
            service.protected_method()

    def test_decorator_allows_valid_auth(self, mock_redis):
        auth = TokenAuth(mock_redis)
        token = auth.register_agent('agent-001')

        class TestService:
            def __init__(self):
                self.agent_id = 'agent-001'
                self._auth_token = token
                self._auth = auth

            @require_auth()
            def protected_method(self):
                return 'success'

        service = TestService()
        result = service.protected_method()
        assert result == 'success'

    def test_decorator_blocks_insufficient_level(self, mock_redis):
        auth = TokenAuth(mock_redis)
        token = auth.register_agent('reader', AuthLevel.READONLY)

        class TestService:
            def __init__(self):
                self.agent_id = 'reader'
                self._auth_token = token
                self._auth = auth

            @require_auth(AuthLevel.ADMIN)
            def admin_only(self):
                return 'admin stuff'

        service = TestService()

        with pytest.raises(AuthError, match='Insufficient permissions'):
            service.admin_only()

    def test_decorator_without_auth_configured(self, mock_redis):
        class TestService:
            def __init__(self):
                self.agent_id = 'agent-001'
                self._auth_token = 'some-token'
                self._auth = None

            @require_auth()
            def protected_method(self):
                return 'success'

        service = TestService()

        with pytest.raises(AuthError, match='Auth not configured'):
            service.protected_method()


class TestTokenHashing:
    """Tests for token hashing security."""

    def test_same_token_produces_same_hash(self, mock_redis):
        auth = TokenAuth(mock_redis)

        hash1 = auth._hash_token('test-token')
        hash2 = auth._hash_token('test-token')

        assert hash1 == hash2

    def test_different_tokens_produce_different_hashes(self, mock_redis):
        auth = TokenAuth(mock_redis)

        hash1 = auth._hash_token('token-1')
        hash2 = auth._hash_token('token-2')

        assert hash1 != hash2

    def test_hash_is_64_chars_sha256(self, mock_redis):
        auth = TokenAuth(mock_redis)
        token_hash = auth._hash_token('any-token')

        assert len(token_hash) == 64
        assert all(c in '0123456789abcdef' for c in token_hash)
