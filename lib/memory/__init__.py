"""Ralph Wiggum Memory Integration

Integrates Claude-Mem for persistent cross-agent memory.

Memory Architecture:

    ┌─────────────────────────────────────────────────────────────┐
    │                    MEMORY LAYERS                             │
    ├─────────────────────────────────────────────────────────────┤
    │                                                              │
    │  PROJECT MEMORY (shared across all agents)                  │
    │  ├── Architecture decisions and rationale                   │
    │  ├── Code patterns discovered                               │
    │  ├── Blockers encountered and solutions                     │
    │  └── Quality standards established                          │
    │                                                              │
    │  TASK MEMORY (shared during task execution)                 │
    │  ├── Task context and requirements                          │
    │  ├── Implementation approach chosen                         │
    │  ├── Artifacts produced                                     │
    │  └── Verification results                                   │
    │                                                              │
    │  AGENT MEMORY (agent-specific learnings)                    │
    │  ├── Personal working context                               │
    │  ├── Files being edited                                     │
    │  ├── Discoveries during implementation                      │
    │  └── Notes for next iteration                               │
    │                                                              │
    └─────────────────────────────────────────────────────────────┘

Usage:
    from lib.memory import ProjectMemory

    memory = ProjectMemory(project_id="my-project", agent_id="agent-frontend")

    # Store a learning
    memory.remember(
        category="architecture",
        content="Using Repository pattern for data access",
        tags=["pattern", "data-layer"]
    )

    # Recall relevant memories before starting work
    context = memory.recall(query="authentication patterns")

    # Store task completion context
    memory.commit_task(
        task_id="task-001",
        summary="Implemented JWT auth",
        learnings=["Used jose library", "Token refresh handled in middleware"]
    )
"""

from .project_memory import ProjectMemory
from .memory_protocol import MemoryProtocol

__all__ = ['ProjectMemory', 'MemoryProtocol']
