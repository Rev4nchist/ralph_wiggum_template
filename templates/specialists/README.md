# Ralph Wiggum Specialist Agents

> *"The right tool for the right job."*

## Overview

Specialists are mode-specific instructions that activate based on task type. Each agent can switch between specialist modes during the development lifecycle.

## Available Specialists

| Specialist | Purpose | Model | Phase |
|------------|---------|-------|-------|
| **code-reviewer** | Quality, security, performance review | minimax | Post-implementation |
| **debugger** | Root cause analysis, bug fixing | glm | When errors occur |
| **test-architect** | Test design, coverage improvement | glm | With features |
| **refactorer** | Code structure, tech debt | glm | Cleanup sprints |
| **security-auditor** | Vulnerability detection, OWASP | minimax | Pre-release |
| **docs-writer** | README, API docs, comments | minimax | Post-feature |

## Activation

Specialists activate based on:
1. **Task category** in PRD: `review`, `test`, `refactor`, `security`, `docs`
2. **Model hint**: `planning`, `implementation`, `verification`
3. **Explicit mode** in task description

## Dev Cycle Integration

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         DEVELOPMENT LIFECYCLE                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  PLAN ──────► IMPLEMENT ──────► VERIFY ──────► RELEASE                  │
│    │              │                │               │                     │
│    │              │                │               │                     │
│    ▼              ▼                ▼               ▼                     │
│                                                                          │
│  [Opus]      [GLM]            [Minimax]       [Minimax]                 │
│              ┌────────┐       ┌────────────┐   ┌────────────┐           │
│              │debugger│       │code-reviewer│  │security-   │           │
│              │        │       │            │   │auditor     │           │
│              │test-   │       │            │   │            │           │
│              │architect│      │            │   │docs-writer │           │
│              │        │       │            │   │            │           │
│              │refactor│       │            │   │            │           │
│              └────────┘       └────────────┘   └────────────┘           │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Usage in PRD

```json
{
  "id": "task-001",
  "category": "feature",
  "description": "Add user authentication",
  "model_hint": "implementation",
  "specialist": null
}

{
  "id": "task-002",
  "category": "review",
  "description": "Security review of auth implementation",
  "model_hint": "verification",
  "specialist": "security-auditor"
}

{
  "id": "task-003",
  "category": "test",
  "description": "Add auth test coverage",
  "model_hint": "implementation",
  "specialist": "test-architect"
}
```

## Specialist Handoffs

Specialists can recommend other specialists:

```
debugger ──► test-architect (add regression test)
code-reviewer ──► security-auditor (deeper security review)
refactorer ──► code-reviewer (review changes)
security-auditor ──► debugger (fix vulnerabilities)
```

## Adding Custom Specialists

Create a new file in `templates/specialists/`:

```markdown
# [Name] Specialist

## Identity
You are **${RALPH_AGENT_ID}** operating in **[name]** mode.

## When to Activate
- [Conditions]

## Model Signal
[MODEL: glm|minimax|opus]

## Protocol
[Steps and patterns]

## Output Format
[Expected deliverables]

## Memory Protocol
[What to store/recall]
```
