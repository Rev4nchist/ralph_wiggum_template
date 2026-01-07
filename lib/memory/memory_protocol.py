"""Memory Protocol - Standard memory operations for agents

Defines the protocol that agents follow for memory operations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any


class MemoryCategory(Enum):
    """Categories for organizing memories."""
    ARCHITECTURE = "architecture"
    PATTERN = "pattern"
    DECISION = "decision"
    BLOCKER = "blocker"
    LEARNING = "learning"
    CONTEXT = "context"
    HANDOFF = "handoff"
    QUALITY = "quality"


class MemoryScope(Enum):
    """Scope determines who can access the memory."""
    PROJECT = "project"
    TASK = "task"
    AGENT = "agent"


@dataclass
class Memory:
    """A single memory entry."""
    id: str
    content: str
    category: str
    scope: str
    project_id: str
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    relevance_score: float = 0.0


@dataclass
class MemoryQuery:
    """Query for retrieving memories."""
    query: str
    project_id: str
    scope: Optional[str] = None
    category: Optional[str] = None
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    limit: int = 10
    min_relevance: float = 0.5


class MemoryProtocol:
    """Protocol defining when and how agents should use memory.

    BEFORE STARTING A TASK:
    1. recall() - Search for relevant project memories
    2. get_task_context() - Get any handoff notes from other agents
    3. get_decisions() - Review architectural decisions

    DURING IMPLEMENTATION:
    1. remember() - Store discoveries and learnings
    2. note_blocker() - Record blockers and solutions
    3. note_pattern() - Record useful patterns discovered

    AFTER COMPLETING A TASK:
    1. commit_task() - Store task summary and learnings
    2. handoff() - Leave notes for agents taking over
    3. update_decisions() - Record any architectural decisions made
    """

    # Memory triggers - when agents MUST interact with memory
    TRIGGERS = {
        "task_start": [
            "recall relevant project memories",
            "check for handoff notes from previous agents",
            "review architectural decisions"
        ],
        "implementation": [
            "store discoveries as they happen",
            "note any patterns that emerge",
            "record blockers and their solutions"
        ],
        "task_complete": [
            "commit task summary",
            "store learnings for future reference",
            "leave handoff notes if task continues"
        ],
        "blocked": [
            "record the blocker with full context",
            "note what was tried",
            "suggest possible solutions"
        ]
    }

    # Memory categories and their purposes
    CATEGORIES = {
        "architecture": "High-level design decisions and rationale",
        "pattern": "Code patterns discovered or established",
        "decision": "Specific technical decisions and why",
        "blocker": "Problems encountered and how they were solved",
        "learning": "General learnings and insights",
        "context": "Current working context for continuity",
        "handoff": "Notes for agents taking over work",
        "quality": "Quality standards and conventions"
    }

    # Tags for cross-referencing memories
    STANDARD_TAGS = [
        "frontend", "backend", "api", "database", "auth",
        "testing", "performance", "security", "refactor",
        "bug-fix", "feature", "documentation"
    ]
