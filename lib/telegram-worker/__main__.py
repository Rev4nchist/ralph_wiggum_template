"""Entry point for running the Telegram queue consumer.

Usage:
    python -m telegram_worker

Environment variables:
    REDIS_URL: Redis connection URL (default: redis://localhost:6379)
    TELEGRAM_SCRIPTS_DIR: Directory containing notify.sh and wait-response.sh (default: ./plans)
"""

import os
import sys

from .consumer import TelegramQueueConsumer


def main() -> None:
    """Start the Telegram queue consumer."""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    scripts_dir = os.environ.get("TELEGRAM_SCRIPTS_DIR", "./plans")

    consumer = TelegramQueueConsumer(
        redis_url=redis_url,
        scripts_dir=scripts_dir
    )

    try:
        consumer.start()
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        consumer.stop()
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
