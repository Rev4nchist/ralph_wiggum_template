"""Telegram Queue Consumer - Consumes ralph:telegram:queue and calls shell scripts."""

import importlib.util
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

# Import from ralph-client/redis_factory (standalone, no relative imports)
_factory_path = Path(__file__).parent.parent / "ralph-client" / "redis_factory.py"
_spec = importlib.util.spec_from_file_location("redis_factory", _factory_path)
_factory_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_factory_module)
create_redis_client = _factory_module.create_redis_client
RedisStartupError = _factory_module.RedisStartupError


class TelegramQueueConsumer:
    """Consumes messages from ralph:telegram:queue and sends via Telegram.

    Uses BRPOP for efficient blocking consumption and calls existing
    shell scripts (notify.sh, wait-response.sh) for Telegram API interaction.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        scripts_dir: str = "./plans",
        shutdown_timeout: int = 30
    ):
        """Initialize the consumer.

        Args:
            redis_url: Redis connection URL
            scripts_dir: Directory containing notify.sh and wait-response.sh
            shutdown_timeout: Seconds to wait for graceful shutdown
        """
        self.redis_url = redis_url
        self.scripts_dir = Path(scripts_dir).resolve()
        self.shutdown_timeout = shutdown_timeout
        self._running = False
        self.redis = None

    def start(self) -> None:
        """Start the consumer with signal handling for graceful shutdown."""
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

        try:
            self.redis = create_redis_client(self.redis_url)
        except RedisStartupError as e:
            print(f"Failed to connect to Redis: {e}", file=sys.stderr)
            sys.exit(1)

        print(f"Telegram consumer started", file=sys.stderr)
        print(f"  Redis: {self.redis_url}", file=sys.stderr)
        print(f"  Scripts: {self.scripts_dir}", file=sys.stderr)

        self._running = True
        self._consume_loop()

    def _consume_loop(self) -> None:
        """Main consumption loop using BRPOP."""
        while self._running:
            try:
                # BRPOP blocks for 5s, then re-checks _running flag
                result = self.redis.brpop("ralph:telegram:queue", timeout=5)
                if result:
                    _, message_json = result
                    try:
                        message = json.loads(message_json)
                        self._process_message(message)
                    except json.JSONDecodeError as e:
                        print(f"Invalid message JSON: {e}", file=sys.stderr)
            except Exception as e:
                if self._running:
                    print(f"Consumer error: {e}", file=sys.stderr)

    def _process_message(self, message: Dict) -> None:
        """Process a single message from the queue.

        Args:
            message: Dict with agent_id, message, level, timestamp
        """
        level = message.get("level", "info")
        content = message.get("message", "")
        agent_id = message.get("agent_id", "unknown")

        # Map level to notify.sh type
        type_map = {
            "info": "status",
            "warning": "status",
            "error": "error",
            "question": "question",
            "complete": "complete",
            "blocked": "blocked"
        }
        msg_type = type_map.get(level, "status")

        print(f"Processing [{level}] from {agent_id}: {content[:50]}...", file=sys.stderr)

        # Call notify.sh
        success = self._run_script("notify.sh", [msg_type, content])

        # For questions, wait for response and store in Redis
        if level == "question" and success:
            response = self._wait_for_response(timeout=300)
            if response:
                key = f"ralph:telegram:response:{agent_id}"
                self.redis.setex(key, 600, response)
                print(f"Response stored for {agent_id}", file=sys.stderr)
            else:
                print(f"No response received for {agent_id}", file=sys.stderr)

    def _run_script(self, script_name: str, args: list) -> bool:
        """Run a shell script with arguments.

        Args:
            script_name: Name of script in scripts_dir
            args: Arguments to pass to script

        Returns:
            True if script succeeded, False otherwise
        """
        script_path = self.scripts_dir / script_name

        if not script_path.exists():
            print(f"Script not found: {script_path}", file=sys.stderr)
            return False

        try:
            result = subprocess.run(
                [str(script_path)] + args,
                timeout=30,
                check=False,
                env={**os.environ},
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                print(f"Script {script_name} failed: {result.stderr}", file=sys.stderr)
                return False
            return True
        except subprocess.TimeoutExpired:
            print(f"Script {script_name} timed out", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Script {script_name} error: {e}", file=sys.stderr)
            return False

    def _wait_for_response(self, timeout: int = 300) -> Optional[str]:
        """Wait for a response using wait-response.sh.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            Response text if received, None otherwise
        """
        script_path = self.scripts_dir / "wait-response.sh"

        if not script_path.exists():
            print(f"wait-response.sh not found", file=sys.stderr)
            return None

        try:
            result = subprocess.run(
                [str(script_path), str(timeout)],
                capture_output=True,
                text=True,
                timeout=timeout + 10  # Extra buffer for script overhead
            )

            if result.returncode == 0:
                # Read response from file
                response_file = self.scripts_dir / ".telegram_response"
                if response_file.exists():
                    content = response_file.read_text().strip()
                    return content.split('\n')[0] if content else None
            return None

        except subprocess.TimeoutExpired:
            print(f"wait-response.sh timed out after {timeout}s", file=sys.stderr)
            return None
        except Exception as e:
            print(f"wait-response.sh error: {e}", file=sys.stderr)
            return None

    def _handle_shutdown(self, signum: int, frame) -> None:
        """Handle shutdown signals gracefully."""
        print(f"\nShutdown requested (signal {signum})", file=sys.stderr)
        self._running = False

    def stop(self) -> None:
        """Stop the consumer."""
        self._running = False
