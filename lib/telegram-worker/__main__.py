"""Entry point for running the Telegram queue consumer.

Usage:
    python -m telegram_worker

Environment variables:
    REDIS_URL: Redis connection URL (default: redis://localhost:6379)
    TELEGRAM_SCRIPTS_DIR: Directory containing notify.sh and wait-response.sh (default: ./plans)
"""

import importlib.util
import os
import sys
from pathlib import Path

# Load consumer module (uses importlib.util to avoid relative import issues)
_this_dir = Path(__file__).parent
_consumer_path = _this_dir / "consumer.py"
_spec = importlib.util.spec_from_file_location("consumer", _consumer_path)
_consumer_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_consumer_module)
TelegramQueueConsumer = _consumer_module.TelegramQueueConsumer


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
