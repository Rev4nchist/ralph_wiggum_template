"""Constants and Redis key patterns for Ralph."""


class RedisKeys:
    """Redis key patterns and prefixes."""

    TASKS_DATA = "ralph:tasks:data"
    TASKS_QUEUE = "ralph:tasks:queue"
    TASKS_CLAIMED = "ralph:tasks:claimed"
    TASKS_BY_STATUS = "ralph:tasks:by_status"

    LOCKS_FILE = "ralph:locks:file"

    AGENTS = "ralph:agents"
    HEARTBEATS = "ralph:heartbeats"

    TOKENS = "ralph:tokens"

    STREAM_EVENTS = "ralph:stream:events"

    EVENTS_CHANNEL = "ralph:events"
    BROADCAST_CHANNEL = "ralph:broadcast"
    MESSAGES_PREFIX = "ralph:messages"

    @classmethod
    def task(cls, task_id: str) -> str:
        return f"{cls.TASKS_DATA}:{task_id}"

    @classmethod
    def task_claimed(cls, task_id: str) -> str:
        return f"{cls.TASKS_CLAIMED}:{task_id}"

    @classmethod
    def tasks_by_status(cls, status: str) -> str:
        return f"{cls.TASKS_BY_STATUS}:{status}"

    @classmethod
    def lock(cls, file_path: str) -> str:
        return f"{cls.LOCKS_FILE}:{file_path}"

    @classmethod
    def heartbeat(cls, agent_id: str) -> str:
        return f"{cls.HEARTBEATS}:{agent_id}"

    @classmethod
    def messages(cls, agent_id: str) -> str:
        return f"{cls.MESSAGES_PREFIX}:{agent_id}"


class TaskStatusConst:
    """Task status constants (string values)."""
    PENDING = "pending"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskTypeConst:
    """Task type constants."""
    IMPLEMENT = "implement"
    DEBUG = "debug"
    REVIEW = "review"
    TEST = "test"
    SECURITY = "security"
    REFACTOR = "refactor"
    DOCS = "docs"
    INTEGRATE = "integrate"


class Defaults:
    """Default configuration values."""
    HEARTBEAT_TTL = 15
    HEARTBEAT_INTERVAL = 5
    TASK_CLAIM_TTL = 3600
    LOCK_TTL = 300
    MAX_RETRIES = 3
    ORPHAN_THRESHOLD_SECONDS = 300
