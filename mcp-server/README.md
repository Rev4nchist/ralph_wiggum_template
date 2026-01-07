# Ralph Wiggum MCP Server

MCP (Model Context Protocol) server for orchestrating Ralph Wiggum autonomous coding agents from Claude Code.

## Installation

```bash
cd mcp-server
npm install
npm run build
```

## Configuration

Add to your Claude Code MCP configuration (`~/.claude/claude_desktop_config.json` or `~/.mcp.json`):

```json
{
  "mcpServers": {
    "ralph": {
      "command": "node",
      "args": ["/path/to/ralph-wiggum-test/mcp-server/dist/index.js"],
      "env": {
        "REDIS_URL": "redis://localhost:6379"
      }
    }
  }
}
```

## Available Tools

### Agent Management

- **ralph_list_agents** - List all active agents with status and capabilities
- **ralph_get_status** - Get detailed status of an agent or task

### Task Orchestration

- **ralph_send_task** - Send task to a specific agent
- **ralph_broadcast_task** - Broadcast task to all agents or filtered by type
- **ralph_get_queue** - View pending tasks
- **ralph_cancel_task** - Cancel a pending task

### File Coordination

- **ralph_lock_file** - Acquire exclusive lock on a file
- **ralph_unlock_file** - Release file lock

### Communication

- **ralph_send_message** - Send message to an agent
- **ralph_get_artifacts** - Retrieve task outputs

## Example Usage in Claude Code

```
# List available agents
Use ralph_list_agents to see active agents

# Send implementation task
Use ralph_send_task with:
  agent_id: "agent-frontend"
  title: "Implement login form"
  description: "Create React login form with email/password validation"
  task_type: "implement"
  priority: 8

# Check task status
Use ralph_get_status with task_id: "task-xyz"

# Coordinate file access
Use ralph_lock_file to prevent conflicts when multiple agents work on shared files
```

## Redis Schema

The MCP server uses Redis for coordination:

- `ralph:agents` - Hash of registered agents
- `ralph:heartbeats:{agent_id}` - Heartbeat keys with TTL
- `ralph:tasks:queue` - Sorted set of pending tasks
- `ralph:tasks:data:{task_id}` - Task details
- `ralph:locks:file:{path}` - File locks
- `ralph:artifacts:{id}` - Task artifacts
- `ralph:messages:{agent_id}` - Pub/sub channels
