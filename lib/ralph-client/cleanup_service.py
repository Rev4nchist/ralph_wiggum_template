"""Background service for orphan task cleanup.

Runs OrphanCleaner.cleanup_orphaned_claims() on a configurable interval
to recover tasks from crashed agents.

Usage:
    python -m lib.ralph_client.cleanup_service

Environment variables:
    REDIS_URL: Redis connection URL (default: redis://localhost:6379)
    CLEANUP_INTERVAL: Seconds between cleanup runs (default: 60)
"""

import os
import sys
import signal
import time
import importlib.util
from pathlib import Path

# Handle imports for both direct execution and Docker
_this_dir = Path(__file__).parent

# Load redis_factory (standalone, no relative imports)
_factory_path = _this_dir / "redis_factory.py"
_spec = importlib.util.spec_from_file_location("redis_factory", _factory_path)
_factory_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_factory_module)
create_redis_client = _factory_module.create_redis_client
RedisStartupError = _factory_module.RedisStartupError

# Load cleanup module (standalone, no relative imports)
_cleanup_path = _this_dir / "cleanup.py"
_spec2 = importlib.util.spec_from_file_location("cleanup", _cleanup_path)
_cleanup_module = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(_cleanup_module)
OrphanCleaner = _cleanup_module.OrphanCleaner


class CleanupService:
    """Background service that periodically cleans up orphaned tasks."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        interval_seconds: int = 60
    ):
        self.redis_url = redis_url
        self.interval = interval_seconds
        self._running = False
        self.redis = None
        self.cleaner = None

    def start(self) -> None:
        """Start the cleanup service with signal handling."""
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

        try:
            self.redis = create_redis_client(self.redis_url)
        except RedisStartupError as e:
            print(f"Failed to connect to Redis: {e}", file=sys.stderr)
            sys.exit(1)

        self.cleaner = OrphanCleaner(self.redis)

        print(f"Cleanup service started", file=sys.stderr)
        print(f"  Redis: {self.redis_url}", file=sys.stderr)
        print(f"  Interval: {self.interval}s", file=sys.stderr)

        self._running = True
        self._cleanup_loop()

    def _cleanup_loop(self) -> None:
        """Main cleanup loop."""
        while self._running:
            try:
                released = self.cleaner.cleanup_orphaned_claims()
                if released:
                    print(
                        f"Released {len(released)} orphaned tasks: {released}",
                        file=sys.stderr
                    )
            except Exception as e:
                print(f"Cleanup error: {e}", file=sys.stderr)

            # Sleep in small increments to allow quick shutdown
            for _ in range(self.interval):
                if not self._running:
                    break
                time.sleep(1)

    def _handle_shutdown(self, signum: int, frame) -> None:
        """Handle shutdown signals gracefully."""
        print(f"\nShutdown requested (signal {signum})", file=sys.stderr)
        self._running = False

    def stop(self) -> None:
        """Stop the cleanup service."""
        self._running = False


def main() -> None:
    """Entry point for cleanup service."""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    interval = int(os.environ.get("CLEANUP_INTERVAL", "60"))

    service = CleanupService(
        redis_url=redis_url,
        interval_seconds=interval
    )

    try:
        service.start()
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        service.stop()
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
