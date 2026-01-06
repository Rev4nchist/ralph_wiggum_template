# Ralph Wiggum Autonomous Coding Ecosystem
## Complete Architecture & Setup Report

**Generated:** 2026-01-06
**Author:** Claude Code + David Hayes
**Version:** 1.0.0

---

## Executive Summary

This document describes a production-ready autonomous coding environment that enables AI-powered development loops to run unattended for extended periods. The system combines four critical components into a unified architecture for long-running, context-aware, documentation-informed AI development.

### Key Capabilities

- **Autonomous Operation**: Runs unattended for hours/days via iterative loops
- **Multi-Model Routing**: Cost-optimized model selection via OpenRouter
- **Persistent Memory**: Context preserved across sessions via Claude-Mem
- **Human-in-the-Loop**: Bidirectional iOS notifications via Telegram
- **Secure Isolation**: DevContainer with network firewall restrictions

---

## System Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              HOST MACHINE                                    │
│                           (Windows Desktop)                                  │
│                                                                              │
│  ┌─────────────────────┐              ┌─────────────────────────────────┐   │
│  │   Claude Code CLI   │              │      Docker Desktop             │   │
│  │   (Interactive)     │              │      (WSL2 Backend)             │   │
│  │                     │              │                                 │   │
│  │  • Direct terminal  │              │  ┌───────────────────────────┐  │   │
│  │  • Manual commands  │    docker    │  │    DevContainer           │  │   │
│  │  • Monitor progress │────exec────▶│  │    (Linux Sandbox)        │  │   │
│  │                     │              │  │                           │  │   │
│  └─────────────────────┘              │  │  ┌─────────────────────┐  │  │   │
│                                       │  │  │   tmux session      │  │  │   │
│                                       │  │  │   "ralph"           │  │  │   │
│                                       │  │  │                     │  │  │   │
│                                       │  │  │  ┌───────────────┐  │  │  │   │
│                                       │  │  │  │ Ralph Wiggum  │  │  │  │   │
│                                       │  │  │  │ Loop Script   │  │  │  │   │
│                                       │  │  │  │               │  │  │  │   │
│                                       │  │  │  │ • PRD Parser  │  │  │  │   │
│                                       │  │  │  │ • Iteration   │  │  │  │   │
│                                       │  │  │  │ • Completion  │  │  │  │   │
│                                       │  │  │  └───────┬───────┘  │  │  │   │
│                                       │  │  │          │          │  │  │   │
│                                       │  │  └──────────┼──────────┘  │  │   │
│                                       │  │             │             │  │   │
│                                       │  │  ┌──────────▼──────────┐  │  │   │
│                                       │  │  │   Claude Code CLI   │  │  │   │
│                                       │  │  │   (Autonomous)      │  │  │   │
│                                       │  │  └──────────┬──────────┘  │  │   │
│                                       │  │             │             │  │   │
│                                       │  └─────────────┼─────────────┘  │   │
│                                       │                │                │   │
│                                       └────────────────┼────────────────┘   │
│                                                        │                    │
└────────────────────────────────────────────────────────┼────────────────────┘
                                                         │
                           ┌─────────────────────────────┼─────────────────────────────┐
                           │                             │                             │
                           ▼                             ▼                             ▼
              ┌─────────────────────┐       ┌─────────────────────┐       ┌─────────────────────┐
              │    OpenRouter API   │       │    Telegram API     │       │   GitHub/npm/PyPI   │
              │                     │       │                     │       │                     │
              │  • Claude Opus 4.5  │       │  • Send updates     │       │  • Git operations   │
              │  • Claude Sonnet 4  │       │  • Receive replies  │       │  • Package installs │
              │  • GLM-4.7          │       │  • iOS push notify  │       │  • Code hosting     │
              │  • Minimax M2.1     │       │                     │       │                     │
              └─────────────────────┘       └──────────┬──────────┘       └─────────────────────┘
                                                       │
                                                       ▼
                                            ┌─────────────────────┐
                                            │    iOS Device       │
                                            │    (Telegram App)   │
                                            │                     │
                                            │  • Notifications    │
                                            │  • Reply to queries │
                                            │  • Monitor progress │
                                            └─────────────────────┘
```

### Component Interaction Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        RALPH WIGGUM ITERATION CYCLE                       │
└──────────────────────────────────────────────────────────────────────────┘

    ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
    │  START  │────▶│  PARSE  │────▶│IMPLEMENT│────▶│ VERIFY  │────▶│ UPDATE  │
    │         │     │   PRD   │     │  TASK   │     │  TESTS  │     │  STATE  │
    └─────────┘     └─────────┘     └─────────┘     └─────────┘     └────┬────┘
                                                                         │
    ┌─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────┐     ┌─────────┐     ┌─────────┐
│  COMMIT │────▶│  CHECK  │────▶│  NEXT   │
│   GIT   │     │COMPLETE?│     │ITERATION│
└─────────┘     └────┬────┘     └─────────┘
                     │
          ┌──────────┴──────────┐
          │                     │
          ▼                     ▼
    ┌───────────┐         ┌───────────┐
    │  ALL DONE │         │  BLOCKED  │
    │  EXIT     │         │  NOTIFY   │
    └───────────┘         └───────────┘
```

---

## Component Details

### 1. DevContainer (Secure Sandbox)

**Purpose**: Provides isolated Linux environment for safe autonomous operation.

**Key Features**:
- Network firewall restricting egress to whitelisted domains only
- Filesystem isolation from host system
- Enables `--dangerously-skip-permissions` for unattended operation
- Persistent volumes for configuration and data

**Whitelisted Domains**:
| Domain | Purpose |
|--------|---------|
| api.anthropic.com | Claude API (direct) |
| openrouter.ai | Model routing API |
| api.telegram.org | iOS notifications |
| github.com | Git operations |
| registry.npmjs.org | npm packages |
| pypi.org | Python packages |
| statsigapi.net | Telemetry |
| sentry.io | Error reporting |

**Configuration Files**:
```
.devcontainer/
├── devcontainer.json    # VS Code container config
├── Dockerfile           # Container image definition
├── init-firewall.sh     # Network isolation rules
└── post-create.sh       # Plugin installation
```

### 2. Ralph Wiggum Loop

**Purpose**: Orchestrates iterative autonomous development cycles.

**Philosophy**: "Don't aim for perfect on first try. Let the loop refine the work."

**Core Mechanism**:
```bash
while iteration <= MAX_ITERATIONS; do
    1. Build prompt with PRD + progress context
    2. Execute Claude Code with task
    3. Check for completion promise
    4. If complete → exit success
    5. If blocked → notify human, wait
    6. Else → continue to next iteration
done
```

**Completion Signals**:
- `<PROMISE>COMPLETE</PROMISE>` - All tasks done
- `<PROMISE>BLOCKED</PROMISE>` - Needs human input
- `<PROMISE>WAITING</PROMISE>` - Awaiting response

**PRD Structure** (plans/prd.json):
```json
{
  "id": "task-001",
  "category": "feature",
  "priority": 1,
  "description": "Task description",
  "acceptance_criteria": ["criterion 1", "criterion 2"],
  "dependencies": [],
  "passes": false,
  "notes": ""
}
```

### 3. OpenRouter Integration

**Purpose**: Cost-optimized multi-model routing for different task types.

**Configuration**:
```bash
ANTHROPIC_BASE_URL="https://openrouter.ai/api"
ANTHROPIC_AUTH_TOKEN="sk-or-v1-..."
ANTHROPIC_API_KEY=""  # Must be blank
```

**Model Strategy**:
| Use Case | Model | Cost/1M tokens |
|----------|-------|----------------|
| Planning/Architecture | Claude Opus 4.5 | $15/$75 |
| Default Execution | z-ai/glm-4.7 | ~$0.30 |
| Background/Long Context | minimax/minimax-m2.1 | ~$0.20 |
| Quick Tasks | Claude Sonnet 4 | $3/$15 |

**Cost Comparison** (20-iteration loop):
- Direct Anthropic: ~$15-25
- OpenRouter (mixed models): ~$4-8

### 4. Telegram Notification System

**Purpose**: Bidirectional communication with human operator via iOS.

**Capabilities**:
- Push notifications for status updates
- Receive text replies from human
- Block and wait for human input when needed
- Progress updates every N iterations

**Message Types**:
| Type | Emoji | When |
|------|-------|------|
| status | 🤖 | General updates |
| question | ❓ | Needs input |
| error | 🔴 | Something failed |
| complete | ✅ | All done |
| blocked | 🚫 | Cannot proceed |

**Flow**:
```
Ralph Loop ──▶ notify.sh ──▶ Telegram API ──▶ iOS Push
                                                  │
Ralph Loop ◀── check-response.sh ◀── User Reply ◀─┘
```

---

## File Structure

```
ralph-wiggum-test/
├── .devcontainer/
│   ├── devcontainer.json      # Container configuration
│   ├── Dockerfile             # Image with Node, Bun, Claude Code
│   ├── init-firewall.sh       # Network whitelist rules
│   └── post-create.sh         # Post-build setup script
│
├── .claude/
│   ├── CLAUDE.md              # Project instructions for AI
│   └── settings.local.json    # Permissions configuration
│
├── .claude-code-router/
│   └── config.json            # Multi-model routing config
│
├── plans/
│   ├── prd.json               # Product Requirements (task list)
│   ├── progress.txt           # Human-readable progress log
│   ├── ralph.sh               # Main orchestration script
│   ├── ralph-openrouter.sh    # OpenRouter variant
│   ├── notify.sh              # Telegram send script
│   ├── check-response.sh      # Telegram receive script
│   ├── wait-response.sh       # Blocking wait for reply
│   └── *.log                  # Execution logs
│
├── src/                       # Source code (created by Ralph)
├── tests/                     # Test files (created by Ralph)
├── dist/                      # Build output
│
├── .env                       # Environment variables (gitignored)
├── package.json               # Node.js dependencies
├── tsconfig.json              # TypeScript configuration
└── jest.config.js             # Test framework config
```

---

## Security Model

### Network Isolation

```
┌─────────────────────────────────────────────────────────────┐
│                    FIREWALL POLICY                           │
├─────────────────────────────────────────────────────────────┤
│  DEFAULT OUTPUT: DROP                                        │
│                                                              │
│  ALLOWED:                                                    │
│  ├── Loopback (localhost)                                   │
│  ├── DNS (UDP/TCP 53)                                       │
│  ├── SSH (TCP 22) - git operations                          │
│  ├── HTTPS (TCP 443) - to whitelisted IPs only             │
│  └── Established connections                                │
│                                                              │
│  BLOCKED:                                                    │
│  └── Everything else (logged as "BLOCKED:")                 │
└─────────────────────────────────────────────────────────────┘
```

### Credential Management

| Credential | Storage | Scope |
|------------|---------|-------|
| ANTHROPIC_API_KEY | .env (gitignored) | Direct API access |
| OPENROUTER_API_KEY | .env (gitignored) | Model routing |
| TELEGRAM_BOT_TOKEN | .env (gitignored) | Notifications |
| TELEGRAM_CHAT_ID | .env (gitignored) | Your chat |

### Safe Autonomous Operation

The `--dangerously-skip-permissions` flag is ONLY safe because:
1. Container is network-isolated (firewall whitelist)
2. Filesystem is isolated from host
3. No access to host credentials (~/.ssh, ~/.aws)
4. Limited egress to known-good domains

---

## Operational Procedures

### Starting Ralph

```bash
# From host (this terminal)
docker exec -d <container_id> bash -c '
  export ANTHROPIC_BASE_URL="https://openrouter.ai/api"
  export ANTHROPIC_AUTH_TOKEN="<openrouter-key>"
  export ANTHROPIC_API_KEY=""
  export TELEGRAM_BOT_TOKEN="<bot-token>"
  export TELEGRAM_CHAT_ID="<chat-id>"
  cd /workspaces/ralph-wiggum-test
  tmux new-session -d -s ralph "bash plans/ralph.sh 20"
'
```

### Monitoring

```bash
# View live output
docker exec <container_id> tmux capture-pane -t ralph -p | tail -30

# Check task status
docker exec <container_id> jq '.[] | {id, passes}' plans/prd.json

# View progress log
docker exec <container_id> tail -50 plans/progress.txt

# Check logs
docker exec <container_id> tail -f plans/ralph.log
```

### Stopping

```bash
# Graceful stop (waits for current iteration)
docker exec <container_id> tmux send-keys -t ralph C-c

# Force stop
docker exec <container_id> tmux kill-session -t ralph
```

### Resuming After Interruption

The system is designed for resume:
1. PRD tracks which tasks passed
2. Progress.txt has context for next iteration
3. Git commits preserve work
4. Simply restart `ralph.sh`

---

## Cost Analysis

### Per-Iteration Costs (estimated)

| Component | Tokens | Cost (OpenRouter) |
|-----------|--------|-------------------|
| Prompt (context) | ~10K | ~$0.03 |
| Response (code) | ~5K | ~$0.08 |
| Tool calls | ~2K | ~$0.02 |
| **Total/iteration** | ~17K | **~$0.13** |

### Project Estimates

| Project Size | Iterations | Est. Cost |
|--------------|------------|-----------|
| Small (5 tasks) | 10-15 | $1.50-2.00 |
| Medium (20 tasks) | 40-60 | $5-8 |
| Large (50 tasks) | 100-150 | $13-20 |

### Cost Optimization Tips

1. Use cheaper models for routine coding (GLM-4.7, Minimax)
2. Reserve Opus for planning/architecture decisions
3. Keep PRD tasks focused and specific
4. Set reasonable MAX_ITERATIONS limits

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| API timeout | Firewall blocking | Add domain to init-firewall.sh |
| No Telegram | Token/ID wrong | Verify with curl test |
| Loop exits early | Completion promise found | Check PRD passes status |
| Tests failing | Missing dependencies | Run npm install |
| Permission denied | Not in container | Use docker exec |

---

## Future Enhancements

### Planned
- [ ] Claude-Mem integration for cross-session memory
- [ ] Librarian documentation search
- [ ] Cost tracking and budget limits
- [ ] Webhook notifications (Slack, Discord)
- [ ] Web dashboard for monitoring

### Potential
- Multi-agent coordination (mcp_agent_mail)
- Automatic PR creation on completion
- Integration with CI/CD pipelines
- Voice notifications via iOS shortcuts

---

## References

- [Ralph Wiggum Plugin](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/ralph-wiggum)
- [Claude Code Plugins](https://www.anthropic.com/news/claude-code-plugins)
- [OpenRouter Documentation](https://openrouter.ai/docs)
- [Claude Code Router](https://github.com/musistudio/claude-code-router)
- [DevContainer Specification](https://containers.dev/)

---

*Report generated by the Ralph Wiggum Autonomous Coding Ecosystem*
