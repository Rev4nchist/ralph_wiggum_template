# Ralph Wiggum Test Project

## Environment

You are operating in a **Ralph Wiggum autonomous development loop** with:
- **Claude-Mem** for persistent memory across sessions
- **Librarian** for up-to-date documentation search
- **DevContainer** isolation for secure unattended operation
- **Telegram notifications** for human-in-the-loop communication

## Workflow Rules

### Before Coding
1. Check `plans/prd.json` for the current task
2. Read `plans/progress.txt` for context from previous iterations
3. Use Librarian to search documentation when uncertain about APIs

### While Coding
1. Follow the acceptance criteria exactly
2. Write tests alongside implementation
3. Use TypeScript strict mode where applicable
4. Commit frequently with descriptive messages

### After Each Task
1. Run tests: `npm test` or `bun test`
2. Run type check if applicable: `npm run typecheck`
3. Update PRD: set `"passes": true` for completed task
4. Update progress.txt with detailed notes
5. Git commit with conventional commit message

### Asking for Human Input
When you need human guidance, use the Telegram notification system:
```bash
./plans/notify.sh "question" "What approach should I use for X?"
```
Then check for response:
```bash
./plans/check-response.sh
```

## Completion Signals
- `<PROMISE>COMPLETE</PROMISE>` - All PRD tasks done
- `<PROMISE>BLOCKED</PROMISE>` - Cannot proceed, needs human input
- `<PROMISE>WAITING</PROMISE>` - Awaiting human response via Telegram

## Code Quality Standards
- TypeScript preferred
- Tests required for non-trivial logic
- No `any` types without justification
- Clear variable/function names

## Librarian Documentation Search

### When to Use Librarian
Use Librarian MCP tools BEFORE implementing code when:
- Working with external libraries (React, Prisma, Zod, etc.)
- Encountering unfamiliar APIs or patterns
- Debugging errors related to third-party code
- Implementing integrations with documented systems

### Available MCP Tools

| Tool | Purpose | Required Args |
|------|---------|---------------|
| `librarian_find_library` | Find library ID for searching | `name` (e.g., "react") |
| `librarian_search` | General documentation search | `query`, `library` |
| `librarian_search_api` | Find API/function docs | `api_name`, `library` |
| `librarian_search_error` | Find error solutions | `error_message` |
| `librarian_list_sources` | List indexed libraries | none |
| `librarian_get_document` | Get full document | `library`, `doc_id`, `slice` |

### Search Modes
- `hybrid` (default): Combines keyword + semantic search
- `word`: Fast keyword-based (BM25) search
- `vector`: Semantic similarity search

### Usage Examples

```yaml
# Step 1: Find the library ID first
librarian_find_library:
  name: "react"
# Returns: reactjs/react.dev

# Step 2: Search documentation
librarian_search:
  query: "useState useEffect custom hooks"
  library: "reactjs/react.dev"
  mode: "hybrid"

# When encountering an error
librarian_search_error:
  error_message: "Cannot read property 'map' of undefined"
  library: "reactjs/react.dev"

# Looking up specific API
librarian_search_api:
  api_name: "useCallback"
  library: "reactjs/react.dev"

# Get full document content
librarian_get_document:
  library: "reactjs/react.dev"
  doc_id: "123"
  slice: "13:29"  # from search results
```

### Indexed Libraries
Use `librarian_list_sources` to see available libraries. Standard sources:
- `reactjs/react.dev` - React documentation
- `tailwindlabs/tailwindcss.com` - Tailwind CSS
- `vercel/next.js` - Next.js
- `prisma/docs` - Prisma ORM
- `colinhacks/zod` - Zod validation

### Best Practices
1. **Search first, code second** - Always check docs before implementing
2. **Use specific queries** - "useState array update" > "react state"
3. **Combine tools** - Use `librarian_search` then `librarian_get_document` for details
4. **Check for errors** - If stuck on an error, use `librarian_search_error`
5. **Verify current APIs** - Library docs may be more current than training data

## Orchestrator Protocol [CRITICAL]

**When executing multi-task projects, you are the ORCHESTRATOR.**

### Core Principle
**NEVER work sequentially on all tasks yourself. ALWAYS spawn specialized subagents.**

### Orchestrator Responsibilities
1. Parse PRD via Taskmaster → `plans/prd.json`
2. Load project context via `ralph_memory_context`
3. Plan execution order respecting dependencies
4. Spawn subagents for parallel execution
5. Monitor progress via `ralph_get_status`
6. Spawn QA agents when implementation complete
7. Aggregate results and report

### Spawn Pattern (All 7 Agent Types)
```yaml
# Agent Types & Keywords (checked in priority order)
code-reviewer: Review, PR, pull request, code review (Minimax)
debugger: Debug, error, fix, bug, failing (GLM)
test-architect: Test, QA, validation, coverage (GLM)
refactorer: Refactor, cleanup, smell, debt (GLM)
security-auditor: Security, audit, vulnerability, OWASP (Minimax)
docs-writer: Docs, README, documentation, guide (Minimax)
backend: API, database, Docker, Python, FastAPI (Opus)
frontend: React, UI, components, CSS, Plasmo (Opus)
general-purpose: Architecture, planning, default (Opus)

# Spawn commands
Task(subagent_type="frontend", prompt="Implement FE-001: [details]")
Task(subagent_type="backend", prompt="Implement BE-001: [details]")
Task(subagent_type="test-architect", prompt="Write tests for AUTH: [details]")
Task(subagent_type="security-auditor", prompt="Audit feature: [details]")
Task(subagent_type="code-reviewer", prompt="Review PR: [details]")
```

### Execution Waves
```yaml
# Parallel when no dependencies
Wave 1: ARCH-001 (no deps)
Wave 2: BE-001 + FE-001 (parallel, both depend on ARCH-001)
Wave 3: FE-002 (depends on BE-001 + FE-001)
Wave 4: QA-001 (depends on all impl tasks)
```

### QA Trigger Points
- After all FE-*/BE-* tasks for a feature complete
- Before marking any feature as done
- After fix agents complete work (re-test)

### What Orchestrators NEVER Do
- Implement code directly (unless single trivial task)
- Work sequentially on multi-task projects
- Skip memory context loading
- Forget to spawn QA after implementation

**Full protocol: `.claude/skills/orchestration/SKILL.md`**

## Memory MCP Tools

Persistent context across agents and sessions.

| Tool | Purpose |
|------|---------|
| `ralph_memory_store` | Store memory with category/tags |
| `ralph_memory_recall` | Search memories by query |
| `ralph_memory_context` | Get project/task context |
| `ralph_memory_handoff` | Leave notes for next agent |

### Memory Categories
- `architecture` - Design decisions
- `pattern` - Discovered patterns
- `blocker` - Issues and resolutions
- `decision` - Key choices made
- `learning` - Knowledge gained
- `general` - Other context

### Usage Pattern
```yaml
# Before starting task
context = ralph_memory_context(task_id="FE-001")
memories = ralph_memory_recall(query="authentication UI patterns")

# While working
ralph_memory_store(content="Using JWT for auth", category="decision")

# After completing task
ralph_memory_handoff(
  task_id="FE-001",
  summary="Implemented login form with validation",
  next_steps=["Add password reset", "Write tests"]
)
```

## Taskmaster Integration

Parse PRDs into executable subtasks.

### Commands
```bash
# Initialize in project
task-master init -y

# Parse PRD to tasks
task-master parse-prd --input .taskmaster/docs/prd.txt --num-tasks 10

# Convert to Ralph format
./scripts/generate-prd.sh . --from-taskmaster
```

### Output Files
- `.taskmaster/tasks/tasks.json` - Taskmaster format
- `plans/prd.json` - Ralph format with dependencies

**Full protocol: `.claude/skills/taskmaster/SKILL.md`**
