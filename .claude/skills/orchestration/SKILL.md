# Orchestration Skill

## Trigger Patterns
- Multi-task PRD detected
- "build project", "implement feature", "create system"
- Multiple tasks with dependencies
- `plans/prd.json` contains 3+ tasks

## Core Protocol [CRITICAL]

**You are the ORCHESTRATOR. You do NOT implement tasks yourself.**

### Your Responsibilities
1. Parse PRD via Taskmaster → `plans/prd.json`
2. Load project context via `ralph_memory_context`
3. Plan execution order (respect dependencies)
4. Spawn specialized subagents via Task tool
5. Monitor progress via `ralph_get_status`
6. Spawn QA when implementation complete
7. Aggregate results and report

### What You NEVER Do
- Implement code directly (unless single trivial task)
- Work sequentially on all tasks yourself
- Skip spawning when parallelization is possible
- Forget to load/save memory context

## Spawn Pattern

```yaml
# For each task in prd.json:
1. Identify agent type from task context
2. Load relevant memories: ralph_memory_recall(task_description)
3. Spawn subagent:

Task(
  subagent_type="frontend",  # or "backend", "qa", "general-purpose"
  prompt="Implement task FE-001: [description]. Context: [memories]"
)
```

### Agent Type Selection (All 7 Specialist Types)

| Task Pattern | Agent Type | Model | Lock Pattern |
|--------------|------------|-------|--------------|
| Review, PR, pull request | code-reviewer | Minimax | `**/*` |
| Debug, error, fix, bug, failing | debugger | GLM | `**/*` |
| Test, QA, validation, coverage | test-architect | GLM | `tests/**/*` |
| Refactor, cleanup, smell, debt | refactorer | GLM | `src/**/*` |
| Security, audit, vulnerability | security-auditor | Minimax | `**/*` |
| Docs, README, documentation | docs-writer | Minimax | `docs/**/*` |
| API, database, Docker, Python | backend | Opus | `backend/**/*` |
| React, UI, components, CSS | frontend | Opus | `src/**/*.tsx` |
| Architecture, planning (default) | general-purpose | Opus | `**/*` |

### Agent Selection Priority
```yaml
Order: Specialist agents checked FIRST → domain agents → default fallback
1. code-reviewer: Post-implementation review
2. debugger: Error/failure occurrence
3. test-architect: Test writing tasks
4. refactorer: Cleanup sprint tasks
5. security-auditor: Pre-release audit
6. docs-writer: Documentation tasks
7. backend: API/database tasks
8. frontend: UI/component tasks
9. general-purpose: Default fallback
```

## Execution Flow

```
1. INIT PHASE
   - ralph_memory_context(project_id)
   - Load plans/prd.json
   - Identify all tasks and dependencies

2. PLAN PHASE
   - Build dependency graph
   - Identify parallelizable tasks
   - Create execution waves

3. EXECUTE PHASE
   For each wave:
     - Spawn agents for independent tasks (parallel)
     - Wait for completion
     - Collect results
     - ralph_memory_store learnings

4. QA PHASE (when all impl tasks complete)
   - Spawn QA agent for each completed feature
   - Collect test results
   - If failures: spawn fix agents

5. COMPLETION PHASE
   - ralph_memory_handoff with project summary
   - Update prd.json with completion status
   - Report to user
```

## Dependency Resolution

```yaml
# Given tasks with dependencies:
ARCH-001: [] (no deps - wave 1)
BE-001: [ARCH-001] (wave 2)
FE-001: [ARCH-001] (wave 2)
FE-002: [BE-001, FE-001] (wave 3)
QA-001: [FE-002] (wave 4)

# Execution:
Wave 1: Spawn ARCH-001
Wave 2: Spawn BE-001 + FE-001 (parallel)
Wave 3: Spawn FE-002
Wave 4: Spawn QA-001
```

## Memory Integration

### Before Spawning Task
```
context = ralph_memory_context(task_id=task.id)
memories = ralph_memory_recall(query=task.description)

# Include in spawn prompt:
"Previous context: {context}
Related memories: {memories}
Your task: {task.description}"
```

### After Task Completion
```
ralph_memory_store(
  content="Completed {task.id}: {summary}",
  category="learning",
  task_id=task.id
)
```

### On Handoff
```
ralph_memory_handoff(
  task_id=task.id,
  summary="Implemented X, Y, Z",
  next_steps=["Test feature", "Deploy"],
  blockers=["API rate limit issue"]
)
```

## QA Trigger Points [CRITICAL]

### Automatic QA Triggers
QA agents MUST be spawned automatically when:

1. **Feature Completion Trigger**
   - All FE-*/BE-* tasks for a feature marked complete
   - Condition: `tasks.filter(t => t.type != 'qa' && t.feature == X).every(t => t.passes)`

2. **Pre-Merge Trigger**
   - Before any feature branch merge
   - Run full test suite + security scan

3. **Fix Verification Trigger**
   - After fix agents complete their work
   - Re-run failed tests + regression suite

4. **Build Success Trigger**
   - After `npm run build` or equivalent succeeds
   - Run E2E tests on built artifacts

### QA Agent Spawn Protocol

```yaml
# Standard QA spawn
Task(
  subagent_type="qa",
  prompt="Test feature: {feature_name}
    Files modified: {file_list}
    Implementation summary: {impl_summary}

    Required checks:
    1. Unit tests for new code
    2. Integration tests for API changes
    3. Build verification
    4. TypeScript strict mode
    5. Security scan for vulnerabilities"
)

# Re-test after fix
Task(
  subagent_type="qa",
  prompt="Re-test feature: {feature_name}
    Previous failures: {failure_list}
    Fix applied: {fix_summary}

    Focus on:
    1. Verify fix resolves issue
    2. Run regression tests
    3. Check for new issues introduced"
)
```

### QA → Fix → Re-QA Cycle

```
QA Agent runs tests
        │
        ▼
   Tests Pass? ─────Yes──────► Feature Complete
        │
       No
        │
        ▼
   Spawn Fix Agent
        │
        ▼
   Fix Agent repairs
        │
        ▼
   Spawn QA Agent (re-test)
        │
        ▼
   (Loop until pass or escalate)
```

### QA Escalation Rules
```yaml
Max Retries: 3 fix attempts
Escalate When:
  - Same test fails 3+ times
  - Fix introduces new failures
  - Security vulnerability detected
  - Build cannot complete

Escalation Actions:
  1. ralph_memory_store(category="blocker", content="...")
  2. Telegram notification to human
  3. Pause further implementation
```

## Error Handling

```yaml
Task Failed:
  1. Log failure: ralph_memory_store(category="blocker")
  2. Analyze cause
  3. Spawn fix agent OR escalate to user

Agent Timeout:
  1. Check ralph_get_status
  2. If stalled > 10min: Cancel and reassign
  3. Log incident

Dependency Blocked:
  1. Identify blocking task
  2. Prioritize blocking task
  3. Resume dependent task after
```

## Example Orchestration Session

```
User: "Build the user authentication feature per PRD"

Orchestrator:
1. Load context: ralph_memory_context()
2. Parse PRD: Found AUTH-001 (backend), AUTH-002 (frontend), AUTH-003 (tests)
3. Dependencies: AUTH-002 depends on AUTH-001, AUTH-003 depends on both

Wave 1:
  Task(subagent_type="backend", prompt="Implement AUTH-001: API endpoints...")

Wave 2: (after AUTH-001 completes)
  Task(subagent_type="frontend", prompt="Implement AUTH-002: Login UI...")

Wave 3: (after AUTH-001 + AUTH-002 complete)
  Task(subagent_type="qa", prompt="Implement AUTH-003: Auth tests...")

4. Aggregate: All tasks passed
5. ralph_memory_handoff(summary="Auth feature complete", next_steps=["Deploy"])
6. Report: "Authentication feature implemented and tested."
```

## Verification Checklist

Before considering orchestration complete:
- [ ] All tasks in prd.json executed
- [ ] No pending dependencies
- [ ] QA run on all features
- [ ] Memory handoff saved
- [ ] User notified of completion
