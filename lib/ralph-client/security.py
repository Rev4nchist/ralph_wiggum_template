"""Security utilities for protecting sensitive data."""
import re
from typing import List, Pattern

SENSITIVE_PATTERNS: List[Pattern] = [
    re.compile(r'(api[_-]?key|token|secret|password|passwd|pwd)\s*[:=]\s*[\'"]?[\w\-]+[\'"]?', re.IGNORECASE),
    re.compile(r'sk-[A-Za-z0-9]{32,}'),
    re.compile(r'sk-ant-[A-Za-z0-9\-]{32,}'),
    re.compile(r'AKIA[A-Z0-9]{16}'),
    re.compile(r'aws[_-]?(secret[_-]?)?access[_-]?key\s*[:=]\s*[\'"]?[\w/+=]+[\'"]?', re.IGNORECASE),
    re.compile(r'gh[pousr]_[A-Za-z0-9_]{36,}'),
    re.compile(r'bearer\s+[\w\-_.~+/]+=*', re.IGNORECASE),
    re.compile(r'(mongodb|postgres|mysql|redis)://[^:]+:[^@]+@', re.IGNORECASE),
    re.compile(r'(DATABASE_URL|REDIS_URL|API_KEY|SECRET_KEY|PRIVATE_KEY)\s*=\s*[\'"]?[^\s\'\"]+[\'"]?', re.IGNORECASE),
]

REDACTED = '[REDACTED]'


def sanitize(message: str) -> str:
    """Remove sensitive data from a message."""
    if not message:
        return message

    result = message
    for pattern in SENSITIVE_PATTERNS:
        result = pattern.sub(REDACTED, result)

    return result


def sanitize_dict(data: dict, sensitive_keys: List[str] = None) -> dict:
    """Recursively sanitize a dictionary, redacting sensitive values."""
    if sensitive_keys is None:
        sensitive_keys = [
            'password', 'passwd', 'pwd', 'secret', 'token', 'api_key',
            'apikey', 'api-key', 'auth', 'authorization', 'credential',
            'private_key', 'privatekey', 'private-key', 'access_key',
            'accesskey', 'access-key', 'secret_key', 'secretkey', 'secret-key'
        ]

    sensitive_keys_lower = [k.lower() for k in sensitive_keys]

    def _sanitize_value(key: str, value, key_is_sensitive: bool = False):
        key_lower = key.lower() if isinstance(key, str) else ''
        is_sensitive_key = any(sk in key_lower for sk in sensitive_keys_lower)

        if isinstance(value, dict):
            return {k: _sanitize_value(k, v) for k, v in value.items()}
        elif isinstance(value, list):
            return [_sanitize_value('', item, is_sensitive_key) for item in value]
        elif is_sensitive_key or key_is_sensitive:
            return REDACTED
        elif isinstance(value, str):
            return sanitize(value)

        return value

    return {k: _sanitize_value(k, v) for k, v in data.items()}


def is_sensitive(text: str) -> bool:
    """Check if text contains sensitive data."""
    if not text:
        return False

    for pattern in SENSITIVE_PATTERNS:
        if pattern.search(text):
            return True

    return False


def mask_partially(value: str, visible_chars: int = 4) -> str:
    """Partially mask a value, showing only first/last few characters."""
    if not value or len(value) <= visible_chars * 2:
        return REDACTED

    return f"{value[:visible_chars]}...{value[-visible_chars:]}"


class SecureLogger:
    """Logger wrapper that sanitizes all output."""

    def __init__(self, logger):
        self._logger = logger

    def _sanitize_args(self, args):
        return tuple(sanitize(str(arg)) if isinstance(arg, str) else arg for arg in args)

    def debug(self, msg, *args, **kwargs):
        self._logger.debug(sanitize(msg), *self._sanitize_args(args), **kwargs)

    def info(self, msg, *args, **kwargs):
        self._logger.info(sanitize(msg), *self._sanitize_args(args), **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._logger.warning(sanitize(msg), *self._sanitize_args(args), **kwargs)

    def error(self, msg, *args, **kwargs):
        self._logger.error(sanitize(msg), *self._sanitize_args(args), **kwargs)

    def critical(self, msg, *args, **kwargs):
        self._logger.critical(sanitize(msg), *self._sanitize_args(args), **kwargs)


class SanitizedException(Exception):
    """Exception that sanitizes its message."""

    def __init__(self, message: str):
        super().__init__(sanitize(message))
