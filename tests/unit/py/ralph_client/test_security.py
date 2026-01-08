"""Unit tests for Ralph security module."""

import pytest
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "lib" / "ralph-client"))

from security import (
    sanitize,
    sanitize_dict,
    is_sensitive,
    mask_partially,
    SecureLogger,
    SanitizedException,
    REDACTED,
)


class TestSanitize:
    """Tests for the sanitize function."""

    def test_sanitize_returns_empty_for_none(self):
        assert sanitize(None) is None

    def test_sanitize_returns_empty_for_empty_string(self):
        assert sanitize('') == ''

    def test_sanitize_openai_api_key(self):
        msg = "Using API key sk-1234567890abcdefghijklmnopqrstuvwxyz12345"
        result = sanitize(msg)
        assert 'sk-1234567890' not in result
        assert REDACTED in result

    def test_sanitize_anthropic_api_key(self):
        msg = "Anthropic key: sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890"
        result = sanitize(msg)
        assert 'sk-ant-' not in result
        assert REDACTED in result

    def test_sanitize_aws_access_key(self):
        msg = "AWS key: AKIAIOSFODNN7EXAMPLE"
        result = sanitize(msg)
        assert 'AKIA' not in result
        assert REDACTED in result

    def test_sanitize_github_token(self):
        msg = "Token: ghp_abcdefghijklmnopqrstuvwxyz1234567890"
        result = sanitize(msg)
        assert 'ghp_' not in result
        assert REDACTED in result

    def test_sanitize_bearer_token(self):
        msg = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = sanitize(msg)
        assert 'eyJhbG' not in result
        assert REDACTED in result

    def test_sanitize_postgres_connection_string(self):
        msg = "postgres://user:password123@localhost:5432/db"
        result = sanitize(msg)
        assert 'password123' not in result
        assert REDACTED in result

    def test_sanitize_mongodb_connection_string(self):
        msg = "mongodb://admin:secretpass@mongo.example.com:27017"
        result = sanitize(msg)
        assert 'secretpass' not in result
        assert REDACTED in result

    def test_sanitize_redis_url(self):
        msg = "redis://default:myredispassword@redis-server:6379"
        result = sanitize(msg)
        assert 'myredispassword' not in result
        assert REDACTED in result

    def test_sanitize_api_key_assignment(self):
        msg = "api_key = 'super-secret-key-123'"
        result = sanitize(msg)
        assert 'super-secret' not in result
        assert REDACTED in result

    def test_sanitize_password_assignment(self):
        msg = "password: mysecretpassword123"
        result = sanitize(msg)
        assert 'mysecretpassword' not in result
        assert REDACTED in result

    def test_sanitize_environment_variable(self):
        msg = "DATABASE_URL=postgres://foo:bar@localhost/db"
        result = sanitize(msg)
        assert 'bar' not in result
        assert REDACTED in result

    def test_sanitize_preserves_safe_content(self):
        msg = "This is a normal message without secrets"
        result = sanitize(msg)
        assert result == msg

    def test_sanitize_multiple_secrets(self):
        msg = "Keys: api_key=secret1 and token: sk-1234567890abcdefghijklmnopqrstuvwxyz12345"
        result = sanitize(msg)
        assert 'secret1' not in result
        assert 'sk-1234567890' not in result
        assert result.count(REDACTED) >= 2


class TestSanitizeDict:
    """Tests for the sanitize_dict function."""

    def test_sanitize_dict_password_key(self):
        data = {'username': 'admin', 'password': 'secret123'}
        result = sanitize_dict(data)

        assert result['username'] == 'admin'
        assert result['password'] == REDACTED

    def test_sanitize_dict_api_key(self):
        data = {'name': 'service', 'api_key': 'sk-123456'}
        result = sanitize_dict(data)

        assert result['name'] == 'service'
        assert result['api_key'] == REDACTED

    def test_sanitize_dict_nested(self):
        data = {
            'service': {
                'name': 'myapp',
                'credentials': {
                    'token': 'secret-token'
                }
            }
        }
        result = sanitize_dict(data)

        assert result['service']['name'] == 'myapp'
        assert result['service']['credentials']['token'] == REDACTED

    def test_sanitize_dict_list_values(self):
        data = {
            'tokens': ['token1', 'token2'],
            'names': ['alice', 'bob']
        }
        result = sanitize_dict(data)

        assert result['tokens'] == [REDACTED, REDACTED]
        assert result['names'] == ['alice', 'bob']

    def test_sanitize_dict_preserves_numbers(self):
        data = {'count': 42, 'password': 'secret'}
        result = sanitize_dict(data)

        assert result['count'] == 42
        assert result['password'] == REDACTED

    def test_sanitize_dict_custom_keys(self):
        data = {'my_custom_secret': 'value', 'safe_field': 'data'}
        result = sanitize_dict(data, sensitive_keys=['my_custom_secret'])

        assert result['my_custom_secret'] == REDACTED
        assert result['safe_field'] == 'data'

    def test_sanitize_dict_string_values_checked(self):
        data = {'message': 'API key is sk-1234567890abcdefghijklmnopqrstuvwxyz12345'}
        result = sanitize_dict(data)

        assert 'sk-1234567890' not in result['message']
        assert REDACTED in result['message']


class TestIsSensitive:
    """Tests for the is_sensitive function."""

    def test_empty_string_not_sensitive(self):
        assert is_sensitive('') is False

    def test_none_not_sensitive(self):
        assert is_sensitive(None) is False

    def test_normal_text_not_sensitive(self):
        assert is_sensitive('Hello, world!') is False

    def test_api_key_is_sensitive(self):
        assert is_sensitive('sk-1234567890abcdefghijklmnopqrstuvwxyz12345') is True

    def test_password_assignment_is_sensitive(self):
        assert is_sensitive('password=secret') is True

    def test_connection_string_is_sensitive(self):
        assert is_sensitive('postgres://user:pass@host/db') is True


class TestMaskPartially:
    """Tests for the mask_partially function."""

    def test_mask_long_value(self):
        result = mask_partially('1234567890abcdef')
        assert result == '1234...cdef'

    def test_mask_short_value_returns_redacted(self):
        result = mask_partially('short')
        assert result == REDACTED

    def test_mask_empty_value(self):
        result = mask_partially('')
        assert result == REDACTED

    def test_mask_none_value(self):
        result = mask_partially(None)
        assert result == REDACTED

    def test_mask_custom_visible_chars(self):
        result = mask_partially('abcdefghijklmnop', visible_chars=2)
        assert result == 'ab...op'


class TestSecureLogger:
    """Tests for the SecureLogger class."""

    def test_debug_sanitizes_message(self):
        mock_logger = MagicMock()
        secure_logger = SecureLogger(mock_logger)

        secure_logger.debug("API key: sk-1234567890abcdefghijklmnopqrstuvwxyz12345")

        mock_logger.debug.assert_called_once()
        call_args = mock_logger.debug.call_args[0][0]
        assert 'sk-1234567890' not in call_args
        assert REDACTED in call_args

    def test_info_sanitizes_message(self):
        mock_logger = MagicMock()
        secure_logger = SecureLogger(mock_logger)

        secure_logger.info("Password: secret123")

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert 'secret123' not in call_args

    def test_warning_sanitizes_message(self):
        mock_logger = MagicMock()
        secure_logger = SecureLogger(mock_logger)

        secure_logger.warning("token=abc123secret")

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args[0][0]
        assert 'abc123secret' not in call_args

    def test_error_sanitizes_message(self):
        mock_logger = MagicMock()
        secure_logger = SecureLogger(mock_logger)

        secure_logger.error("Failed with api_key: mysecret")

        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args[0][0]
        assert 'mysecret' not in call_args

    def test_critical_sanitizes_message(self):
        mock_logger = MagicMock()
        secure_logger = SecureLogger(mock_logger)

        secure_logger.critical("postgres://user:pass@host/db failed")

        mock_logger.critical.assert_called_once()
        call_args = mock_logger.critical.call_args[0][0]
        assert 'pass' not in call_args or REDACTED in call_args

    def test_sanitizes_string_args(self):
        mock_logger = MagicMock()
        secure_logger = SecureLogger(mock_logger)

        secure_logger.info("Message: %s", "token=secret123")

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0]
        assert 'secret123' not in str(call_args)


class TestSanitizedException:
    """Tests for the SanitizedException class."""

    def test_exception_sanitizes_message(self):
        exc = SanitizedException("Failed with api_key=secret123")

        assert 'secret123' not in str(exc)
        assert REDACTED in str(exc)

    def test_exception_preserves_safe_message(self):
        exc = SanitizedException("Something went wrong")

        assert str(exc) == "Something went wrong"

    def test_exception_is_catchable(self):
        with pytest.raises(SanitizedException):
            raise SanitizedException("Error with password=test")

    def test_exception_inherits_from_exception(self):
        exc = SanitizedException("test")
        assert isinstance(exc, Exception)


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_sanitize_case_insensitive_keys(self):
        data = {
            'PASSWORD': 'secret1',
            'Api_Key': 'secret2',
            'TOKEN': 'secret3'
        }
        result = sanitize_dict(data)

        assert result['PASSWORD'] == REDACTED
        assert result['Api_Key'] == REDACTED
        assert result['TOKEN'] == REDACTED

    def test_sanitize_partial_key_match(self):
        data = {
            'user_password_hash': 'abc123',
            'api_key_v2': 'xyz789',
            'oauth_token_expiry': 'never'
        }
        result = sanitize_dict(data)

        assert result['user_password_hash'] == REDACTED
        assert result['api_key_v2'] == REDACTED
        assert result['oauth_token_expiry'] == REDACTED

    def test_sanitize_mixed_content(self):
        msg = """
        Config file:
        api_key = 'sk-test123'
        database_url = 'postgres://admin:pass@localhost/db'
        debug = true
        """
        result = sanitize(msg)

        assert 'sk-test123' not in result
        assert 'pass@localhost' not in result
        assert 'debug = true' in result

    def test_deeply_nested_dict(self):
        data = {
            'level1': {
                'level2': {
                    'level3': {
                        'secret': 'deeply-hidden'
                    }
                }
            }
        }
        result = sanitize_dict(data)

        assert result['level1']['level2']['level3']['secret'] == REDACTED
