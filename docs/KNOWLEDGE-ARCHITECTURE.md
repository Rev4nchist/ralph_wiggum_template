# Ralph Wiggum Knowledge Architecture

> *"Technology married with liberal arts yields results that make our hearts sing."*

---

## The Three Minds

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         AGENT KNOWLEDGE SYSTEM                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    LIBRARIAN (External Knowledge)                 │  │
│  │                                                                    │  │
│  │  "What does the world know?"                                      │  │
│  │                                                                    │  │
│  │  • Documentation for libraries and frameworks                     │  │
│  │  • Best practices and patterns                                    │  │
│  │  • API references and specifications                              │  │
│  │  • Up-to-date information from official sources                   │  │
│  │                                                                    │  │
│  │  Usage: librarian search --library <name> "<query>"               │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                 │                                        │
│                                 ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                   CLAUDE-MEM (Persistent Memory)                  │  │
│  │                                                                    │  │
│  │  "What has the project learned?"                                  │  │
│  │                                                                    │  │
│  │  • Architecture decisions and rationale                           │  │
│  │  • Code patterns discovered                                       │  │
│  │  • Blockers encountered and solutions                             │  │
│  │  • Handoff notes between agents                                   │  │
│  │  • Quality standards established                                  │  │
│  │                                                                    │  │
│  │  Survives: Across sessions, container restarts, agent changes     │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                 │                                        │
│                                 ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                      REDIS (Working Memory)                       │  │
│  │                                                                    │  │
│  │  "What's happening right now?"                                    │  │
│  │                                                                    │  │
│  │  • Task queue and assignments                                     │  │
│  │  • File locks (who's editing what)                                │  │
│  │  • Agent registry (who's alive)                                   │  │
│  │  • Real-time events and messages                                  │  │
│  │                                                                    │  │
│  │  Ephemeral: Coordination data, replaced on restart                │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Memory Flow

### Before a Task

```
Agent receives task
        │
        ▼
┌───────────────────┐
│ 1. RECALL MEMORY  │
│                   │
│ • Project context │
│ • Past decisions  │
│ • Handoff notes   │
│ • Relevant patterns│
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ 2. SEARCH DOCS    │
│                   │
│ • API references  │
│ • Best practices  │
│ • Examples        │
└───────┬───────────┘
        │
        ▼
   Begin with full context
```

### During a Task

```
Implementation in progress
        │
        ├──► Discovery? ──► memory.note_pattern()
        │
        ├──► Decision? ──► memory.note_architecture()
        │
        ├──► Blocker? ──► memory.note_blocker()
        │
        └──► Unknown API? ──► librarian search
```

### After a Task

```
Task complete
        │
        ▼
┌───────────────────┐
│ 1. COMMIT TASK    │
│                   │
│ • Summary         │
│ • Learnings       │
│ • Artifacts       │
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│ 2. HANDOFF        │
│                   │
│ • Next steps      │
│ • Notes for others│
│ • Dependencies    │
└───────┬───────────┘
        │
        ▼
   Knowledge preserved for future agents
```

---

## Memory Categories

| Category | Purpose | Example |
|----------|---------|---------|
| `architecture` | Design decisions | "Using Repository pattern for data access" |
| `pattern` | Code patterns to follow | "All API calls use standardized error handling" |
| `decision` | Technical choices | "Chose jose over jsonwebtoken for edge runtime" |
| `blocker` | Problems and solutions | "ESM modules fixed with transformIgnorePatterns" |
| `learning` | Insights gained | "Middleware pattern cleaner than per-route auth" |
| `handoff` | Notes for next agent | "Auth complete, frontend can now integrate" |
| `quality` | Standards established | "All components must have unit tests" |

---

## Multi-Agent Memory Sharing

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Agent A   │     │   Agent B   │     │   Agent C   │
│  (Frontend) │     │  (Backend)  │     │(Integration)│
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │    ┌──────────────┴──────────────┐    │
       │    │                              │    │
       ▼    ▼                              ▼    ▼
┌─────────────────────────────────────────────────────┐
│                   SHARED MEMORY                      │
│                                                      │
│  project:my-app:architecture  ◄── All agents write  │
│  project:my-app:patterns      ◄── All agents read   │
│  project:my-app:blockers                             │
│                                                      │
│  task:001:context            ◄── Task-specific      │
│  task:001:handoff                                    │
│                                                      │
│  agent:frontend:working      ◄── Agent-specific     │
│  agent:backend:working                               │
│                                                      │
└─────────────────────────────────────────────────────┘
```

---

## Librarian Integration

### Setup per Project

```yaml
# .librarian/libraries.yml
sources:
  # Add libraries your project uses
  - url: https://github.com/vercel/next.js
    docs: docs
    ref: canary

  - url: https://github.com/prisma/prisma
    docs: docs
    ref: main

  - url: https://github.com/trpc/trpc
    docs: www/docs
    ref: main
```

### Usage During Development

```bash
# Before implementing a feature
librarian search --library nextjs "app router data fetching"

# When encountering an error
librarian search --library prisma "relation not found error"

# Looking for patterns
librarian search --library react "form validation patterns"
```

### Research Protocol

1. **Identify** — What do I need to know?
2. **Search** — Query Librarian for documentation
3. **Understand** — Read and comprehend the recommended approach
4. **Implement** — Follow best practices
5. **Remember** — Store learnings in Claude-Mem for future reference

---

## The Virtuous Cycle

```
                    ┌─────────────────────┐
                    │                     │
                    ▼                     │
        ┌─────────────────────┐           │
        │   LIBRARIAN         │           │
        │   (Learn from docs) │           │
        └──────────┬──────────┘           │
                   │                      │
                   ▼                      │
        ┌─────────────────────┐           │
        │   IMPLEMENT         │           │
        │   (Apply knowledge) │           │
        └──────────┬──────────┘           │
                   │                      │
                   ▼                      │
        ┌─────────────────────┐           │
        │   CLAUDE-MEM        │           │
        │   (Store learnings) │───────────┘
        └─────────────────────┘

Each cycle makes the system smarter.
Future agents benefit from past learnings.
```

---

## Implementation

### Memory Library (`lib/memory/`)

```python
from lib.memory import ProjectMemory

memory = ProjectMemory(
    project_id="my-project",
    agent_id="agent-frontend"
)

# Store learnings
memory.note_architecture(decision, rationale, alternatives)
memory.note_pattern(name, description, example)
memory.note_blocker(problem, solution, attempts)

# Recall context
context = memory.get_project_context()
task_ctx = memory.get_task_context(task_id)

# Handoff to other agents
memory.handoff(task_id, summary, next_steps, notes)

# Commit task completion
memory.commit_task(task_id, summary, learnings, artifacts)
```

---

*Every memory stored makes the next agent wiser.*
*Every pattern documented prevents the next blocker.*
*Every handoff note enables seamless continuity.*

**The system learns. The system improves. The system crafts better code.**
