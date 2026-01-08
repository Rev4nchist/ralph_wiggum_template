"""P0 Critical Tests: File Lock Coordination.

Tests the FileLock class which prevents concurrent file edits via pessimistic locking.
Uses Redis SET with NX (only if not exists) and EX (expiration) for atomic lock acquisition.
"""

import json
import time
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "lib" / "ralph-client"))

from locks import FileLock


class TestFileLockAcquisition:
    """P0 Critical: File lock prevents concurrent edits."""

    @pytest.fixture
    def lock(self, mock_redis, agent_id):
        return FileLock(mock_redis, agent_id)

    @pytest.fixture
    def other_lock(self, mock_redis, other_agent_id):
        return FileLock(mock_redis, other_agent_id)

    @pytest.mark.p0
    def test_acquire_succeeds_when_unlocked(self, lock, mock_redis):
        """Can acquire lock on unlocked file."""
        result = lock.acquire("/path/to/file.py")

        assert result is True
        assert mock_redis.exists("ralph:locks:file::path:to:file.py")

    @pytest.mark.p0
    def test_acquire_fails_when_held_by_other(self, lock, other_lock, mock_redis):
        """Cannot acquire lock held by another agent."""
        lock.acquire("/path/to/contested.py")

        result = other_lock.acquire("/path/to/contested.py")

        assert result is False

    @pytest.mark.p0
    def test_acquire_succeeds_for_same_agent(self, lock, mock_redis):
        """Same agent can re-acquire (extend) their own lock."""
        lock.acquire("/path/to/owned.py")

        result = lock.acquire("/path/to/owned.py")

        assert result is True

    @pytest.mark.p0
    def test_lock_has_ttl(self, lock, mock_redis):
        """Lock has TTL to prevent deadlock."""
        lock.acquire("/path/to/ttl.py", ttl=300)

        ttl = mock_redis.ttl("ralph:locks:file::path:to:ttl.py")

        assert ttl > 0
        assert ttl <= 300


class TestFileLockRelease:
    """P0 Critical: Lock release and cleanup."""

    @pytest.fixture
    def lock(self, mock_redis, agent_id):
        return FileLock(mock_redis, agent_id)

    @pytest.fixture
    def other_lock(self, mock_redis, other_agent_id):
        return FileLock(mock_redis, other_agent_id)

    @pytest.mark.p0
    def test_release_own_lock(self, lock, mock_redis):
        """Can release own lock."""
        lock.acquire("/path/to/release.py")

        result = lock.release("/path/to/release.py")

        assert result is True
        assert not mock_redis.exists("ralph:locks:file::path:to:release.py")

    @pytest.mark.p0
    def test_cannot_release_other_lock(self, lock, other_lock, mock_redis):
        """Cannot release lock held by another agent."""
        lock.acquire("/path/to/other.py")

        result = other_lock.release("/path/to/other.py")

        assert result is False
        assert mock_redis.exists("ralph:locks:file::path:to:other.py")

    @pytest.mark.p0
    def test_release_all_releases_all_held(self, lock, mock_redis):
        """release_all releases all locks held by agent."""
        lock.acquire("/file1.py")
        lock.acquire("/file2.py")
        lock.acquire("/file3.py")

        lock.release_all()

        assert not mock_redis.exists("ralph:locks:file::file1.py")
        assert not mock_redis.exists("ralph:locks:file::file2.py")
        assert not mock_redis.exists("ralph:locks:file::file3.py")


class TestFileLockWaiting:
    """P1 High: Lock waiting and polling."""

    @pytest.fixture
    def lock(self, mock_redis, agent_id):
        return FileLock(mock_redis, agent_id)

    @pytest.fixture
    def other_lock(self, mock_redis, other_agent_id):
        return FileLock(mock_redis, other_agent_id)

    @pytest.mark.p1
    def test_wait_for_lock_returns_immediately_if_available(self, lock, mock_redis):
        """wait_for_lock returns quickly if lock is free."""
        start = time.time()

        result = lock.wait_for_lock("/available.py", timeout=5)

        elapsed = time.time() - start
        assert result is True
        assert elapsed < 1

    @pytest.mark.p1
    def test_wait_for_lock_times_out(self, lock, other_lock, mock_redis):
        """wait_for_lock times out if lock not released."""
        other_lock.acquire("/blocked.py")

        result = lock.wait_for_lock("/blocked.py", timeout=0.5, poll_interval=0.1)

        assert result is False

    @pytest.mark.p1
    def test_extend_updates_ttl(self, lock, mock_redis):
        """extend() refreshes the lock TTL."""
        lock.acquire("/extend.py", ttl=60)
        original_ttl = mock_redis.ttl("ralph:locks:file::extend.py")

        lock.extend("/extend.py", ttl=300)

        new_ttl = mock_redis.ttl("ralph:locks:file::extend.py")
        assert new_ttl > original_ttl


class TestFileLockInfo:
    """P2 Medium: Lock information queries."""

    @pytest.fixture
    def lock(self, mock_redis, agent_id):
        return FileLock(mock_redis, agent_id)

    @pytest.mark.p2
    def test_get_lock_info_returns_data(self, lock, mock_redis, agent_id):
        """get_lock_info returns lock metadata."""
        lock.acquire("/info.py", ttl=300)

        info = lock.get_lock_info("/info.py")

        assert info is not None
        assert info["agent_id"] == agent_id
        assert info["file_path"] == "/info.py"
        assert "acquired_at" in info

    @pytest.mark.p2
    def test_get_lock_info_returns_none_if_unlocked(self, lock, mock_redis):
        """get_lock_info returns None for unlocked file."""
        info = lock.get_lock_info("/unlocked.py")

        assert info is None

    @pytest.mark.p2
    def test_is_owned_by_me(self, lock, mock_redis):
        """is_owned_by_me returns True for own lock."""
        lock.acquire("/self.py")

        assert lock.is_owned_by_me("/self.py") is True
        assert lock.is_owned_by_me("/other.py") is False
