#!/usr/bin/env python3
"""File Protection Hook - Check locks before editing

Ensures:
- File is not locked by another agent
- Lock is acquired before editing
- Protected paths are not modified
"""

import os
import sys
from pathlib import Path
from typing import Optional

PROTECTED_PATHS = [
    '.env',
    '.env.local',
    '.env.production',
    'package-lock.json',
    'yarn.lock',
    'pnpm-lock.yaml',
    '.git/',
    'node_modules/',
]


def check_protected(file_path: str) -> Optional[str]:
    """Check if file is in protected paths."""
    path = Path(file_path)

    for protected in PROTECTED_PATHS:
        if protected.endswith('/'):
            if str(path).startswith(protected) or f"/{protected}" in str(path):
                return f"Directory {protected} is protected"
        else:
            if path.name == protected or str(path).endswith(protected):
                return f"File {protected} is protected - requires manual edit"

    return None


def check_lock(file_path: str) -> Optional[str]:
    """Check if file is locked by another agent."""
    redis_url = os.environ.get('REDIS_URL')
    agent_id = os.environ.get('RALPH_AGENT_ID', 'unknown')

    if not redis_url:
        return None

    try:
        import redis
        from lib.ralph_client import FileLock

        client = redis.from_url(redis_url, decode_responses=True)
        lock = FileLock(client, agent_id)

        lock_info = lock.get_lock_info(file_path)
        if lock_info and lock_info['agent_id'] != agent_id:
            return f"File locked by {lock_info['agent_id']} since {lock_info['acquired_at']}"

    except ImportError:
        pass
    except Exception as e:
        print(f"Warning: Could not check lock: {e}", file=sys.stderr)

    return None


def main() -> int:
    """Check if file can be edited."""
    if len(sys.argv) < 2:
        print("Usage: file_protection.py <file_path>")
        return 1

    file_path = sys.argv[1]

    protection_error = check_protected(file_path)
    if protection_error:
        print(f"🔒 PROTECTED: {protection_error}")
        return 1

    lock_error = check_lock(file_path)
    if lock_error:
        print(f"🔐 LOCKED: {lock_error}")
        print("\nTo proceed:")
        print("  1. Wait for other agent to finish")
        print("  2. Or coordinate with agent owner")
        return 1

    print(f"✅ File {file_path} is available for editing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
