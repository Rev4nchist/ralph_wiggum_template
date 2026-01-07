#!/usr/bin/env node
/**
 * Ralph Wiggum MCP Server
 *
 * Provides tools for Claude Code to orchestrate Ralph agents:
 * - ralph_list_agents: List active agents
 * - ralph_send_task: Send task to specific agent
 * - ralph_broadcast_task: Broadcast task to all agents
 * - ralph_get_status: Get agent/task status
 * - ralph_lock_file: Acquire file lock
 * - ralph_unlock_file: Release file lock
 * - ralph_get_artifacts: Retrieve task artifacts
 * - ralph_send_message: Send message to agent
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ToolSchema,
} from "@modelcontextprotocol/sdk/types.js";
import Redis from "ioredis";
import { z } from "zod";

const REDIS_URL = process.env.REDIS_URL || "redis://localhost:6379";

let redis: Redis;

// =============================================================================
// Cycle Detection for Task Dependencies
// =============================================================================

interface DependencyGraph {
  [taskId: string]: string[];
}

async function buildDependencyGraph(): Promise<DependencyGraph> {
  const graph: DependencyGraph = {};

  for await (const key of redis.scanStream({ match: "ralph:tasks:data:*" })) {
    const data = await redis.get(key as string);
    if (data) {
      const task = JSON.parse(data);
      graph[task.id] = task.deps || task.dependencies || [];
    }
  }

  return graph;
}

function detectCycle(
  graph: DependencyGraph,
  newTaskId: string,
  newDeps: string[]
): { hasCycle: boolean; cycle?: string[] } {
  const tempGraph = { ...graph, [newTaskId]: newDeps };

  const visited = new Set<string>();
  const recStack = new Set<string>();
  const path: string[] = [];

  function dfs(node: string): string[] | null {
    if (recStack.has(node)) {
      const cycleStart = path.indexOf(node);
      return [...path.slice(cycleStart), node];
    }

    if (visited.has(node)) return null;

    visited.add(node);
    recStack.add(node);
    path.push(node);

    const deps = tempGraph[node] || [];
    for (const dep of deps) {
      const cycle = dfs(dep);
      if (cycle) return cycle;
    }

    path.pop();
    recStack.delete(node);
    return null;
  }

  for (const node of Object.keys(tempGraph)) {
    if (!visited.has(node)) {
      const cycle = dfs(node);
      if (cycle) {
        return { hasCycle: true, cycle };
      }
    }
  }

  return { hasCycle: false };
}

async function validateDependencies(
  taskId: string,
  dependencies: string[]
): Promise<{ valid: boolean; error?: string; cycle?: string[] }> {
  if (!dependencies || dependencies.length === 0) {
    return { valid: true };
  }

  // Check all dependencies exist
  for (const depId of dependencies) {
    const exists = await redis.exists(`ralph:tasks:data:${depId}`);
    if (!exists) {
      return { valid: false, error: `Dependency task not found: ${depId}` };
    }
  }

  // Check for self-dependency
  if (dependencies.includes(taskId)) {
    return { valid: false, error: "Task cannot depend on itself", cycle: [taskId, taskId] };
  }

  // Check for cycles
  const graph = await buildDependencyGraph();
  const result = detectCycle(graph, taskId, dependencies);

  if (result.hasCycle) {
    return {
      valid: false,
      error: `Circular dependency detected: ${result.cycle?.join(" → ")}`,
      cycle: result.cycle,
    };
  }

  return { valid: true };
}

try {
  redis = new Redis(REDIS_URL);
} catch (e) {
  console.error("Failed to connect to Redis:", e);
  process.exit(1);
}

const server = new Server(
  {
    name: "ralph-orchestrator",
    version: "0.1.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

const TOOLS: Record<string, z.ZodSchema> = {
  ralph_list_agents: z.object({}),

  ralph_send_task: z.object({
    agent_id: z.string().describe("Target agent ID"),
    title: z.string().describe("Task title"),
    description: z.string().describe("Task description"),
    task_type: z
      .enum(["implement", "debug", "review", "test", "security", "refactor", "docs"])
      .default("implement"),
    priority: z.number().min(1).max(10).default(5),
    files: z.array(z.string()).optional(),
    acceptance_criteria: z.array(z.string()).optional(),
    dependencies: z.array(z.string()).optional().describe("Task IDs this task depends on"),
  }),

  ralph_broadcast_task: z.object({
    title: z.string().describe("Task title"),
    description: z.string().describe("Task description"),
    task_type: z.string().default("implement"),
    target_type: z.string().optional().describe("Target agent type (frontend, backend, etc)"),
  }),

  ralph_get_status: z.object({
    agent_id: z.string().optional(),
    task_id: z.string().optional(),
  }),

  ralph_lock_file: z.object({
    file_path: z.string().describe("Path to lock"),
    agent_id: z.string().describe("Agent requesting lock"),
    ttl: z.number().default(300).describe("Lock TTL in seconds"),
  }),

  ralph_unlock_file: z.object({
    file_path: z.string().describe("Path to unlock"),
    agent_id: z.string().describe("Agent releasing lock"),
  }),

  ralph_get_artifacts: z.object({
    task_id: z.string().optional(),
    agent_id: z.string().optional(),
  }),

  ralph_send_message: z.object({
    target_agent: z.string().describe("Target agent ID"),
    message_type: z.string().describe("Message type"),
    payload: z.record(z.any()).describe("Message payload"),
  }),

  ralph_get_queue: z.object({
    limit: z.number().default(20),
    status: z.string().optional(),
  }),

  ralph_cancel_task: z.object({
    task_id: z.string().describe("Task to cancel"),
  }),

  ralph_validate_deps: z.object({
    task_id: z.string().describe("Task ID to validate"),
    dependencies: z.array(z.string()).describe("Proposed dependencies"),
  }),
};

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "ralph_list_agents",
        description: "List all active Ralph agents with their status and capabilities",
        inputSchema: {
          type: "object",
          properties: {},
          required: [],
        },
      },
      {
        name: "ralph_send_task",
        description: "Send a task to a specific Ralph agent",
        inputSchema: {
          type: "object",
          properties: {
            agent_id: { type: "string", description: "Target agent ID" },
            title: { type: "string", description: "Task title" },
            description: { type: "string", description: "Detailed task description" },
            task_type: {
              type: "string",
              enum: ["implement", "debug", "review", "test", "security", "refactor", "docs"],
              default: "implement",
            },
            priority: { type: "number", minimum: 1, maximum: 10, default: 5 },
            files: { type: "array", items: { type: "string" }, description: "Files involved" },
            acceptance_criteria: { type: "array", items: { type: "string" } },
            dependencies: { type: "array", items: { type: "string" }, description: "Task IDs this depends on" },
          },
          required: ["agent_id", "title", "description"],
        },
      },
      {
        name: "ralph_broadcast_task",
        description: "Broadcast a task to all agents or agents of a specific type",
        inputSchema: {
          type: "object",
          properties: {
            title: { type: "string" },
            description: { type: "string" },
            task_type: { type: "string", default: "implement" },
            target_type: { type: "string", description: "Filter by agent type" },
          },
          required: ["title", "description"],
        },
      },
      {
        name: "ralph_get_status",
        description: "Get status of an agent or task",
        inputSchema: {
          type: "object",
          properties: {
            agent_id: { type: "string", description: "Agent to check" },
            task_id: { type: "string", description: "Task to check" },
          },
        },
      },
      {
        name: "ralph_lock_file",
        description: "Acquire a file lock for an agent",
        inputSchema: {
          type: "object",
          properties: {
            file_path: { type: "string" },
            agent_id: { type: "string" },
            ttl: { type: "number", default: 300 },
          },
          required: ["file_path", "agent_id"],
        },
      },
      {
        name: "ralph_unlock_file",
        description: "Release a file lock",
        inputSchema: {
          type: "object",
          properties: {
            file_path: { type: "string" },
            agent_id: { type: "string" },
          },
          required: ["file_path", "agent_id"],
        },
      },
      {
        name: "ralph_get_artifacts",
        description: "Get artifacts produced by tasks or agents",
        inputSchema: {
          type: "object",
          properties: {
            task_id: { type: "string" },
            agent_id: { type: "string" },
          },
        },
      },
      {
        name: "ralph_send_message",
        description: "Send a message to a specific agent",
        inputSchema: {
          type: "object",
          properties: {
            target_agent: { type: "string" },
            message_type: { type: "string" },
            payload: { type: "object" },
          },
          required: ["target_agent", "message_type", "payload"],
        },
      },
      {
        name: "ralph_get_queue",
        description: "Get tasks in the queue",
        inputSchema: {
          type: "object",
          properties: {
            limit: { type: "number", default: 20 },
            status: { type: "string" },
          },
        },
      },
      {
        name: "ralph_cancel_task",
        description: "Cancel a pending or claimed task",
        inputSchema: {
          type: "object",
          properties: {
            task_id: { type: "string" },
          },
          required: ["task_id"],
        },
      },
      {
        name: "ralph_validate_deps",
        description: "Validate task dependencies for circular references before creating a task",
        inputSchema: {
          type: "object",
          properties: {
            task_id: { type: "string", description: "The task ID to validate" },
            dependencies: { type: "array", items: { type: "string" }, description: "Proposed dependency task IDs" },
          },
          required: ["task_id", "dependencies"],
        },
      },
    ],
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case "ralph_list_agents": {
        const agents = await redis.hgetall("ralph:agents");
        const result = [];

        for (const [id, data] of Object.entries(agents)) {
          const agent = JSON.parse(data);
          const isAlive = await redis.exists(`ralph:heartbeats:${id}`);
          result.push({ ...agent, is_alive: isAlive > 0 });
        }

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(result, null, 2),
            },
          ],
        };
      }

      case "ralph_send_task": {
        const taskId = `task-${Date.now().toString(36)}`;
        const dependencies = (args as any).dependencies || [];

        // Validate dependencies for cycles
        if (dependencies.length > 0) {
          const validation = await validateDependencies(taskId, dependencies);
          if (!validation.valid) {
            return {
              content: [
                {
                  type: "text",
                  text: JSON.stringify({
                    success: false,
                    error: validation.error,
                    cycle: validation.cycle,
                  }),
                },
              ],
              isError: true,
            };
          }
        }

        const task = {
          id: taskId,
          ...args,
          deps: dependencies,
          status: "pending",
          created_at: new Date().toISOString(),
          created_by: "claude-code",
        };

        await redis.set(`ralph:tasks:data:${taskId}`, JSON.stringify(task));

        const priority = (args as any).priority || 5;
        const score = (10 - priority) * 1000000 + Date.now();
        await redis.zadd("ralph:tasks:queue", score, taskId);

        await redis.publish(
          `ralph:messages:${(args as any).agent_id}`,
          JSON.stringify({
            type: "new_task",
            task_id: taskId,
            from: "claude-code",
            timestamp: new Date().toISOString(),
          })
        );

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({ success: true, task_id: taskId }),
            },
          ],
        };
      }

      case "ralph_broadcast_task": {
        const taskId = `task-${Date.now().toString(36)}`;
        const task = {
          id: taskId,
          ...args,
          status: "pending",
          created_at: new Date().toISOString(),
          created_by: "claude-code",
        };

        await redis.set(`ralph:tasks:data:${taskId}`, JSON.stringify(task));

        const score = 5 * 1000000 + Date.now();
        await redis.zadd("ralph:tasks:queue", score, taskId);

        await redis.publish(
          "ralph:broadcast",
          JSON.stringify({
            type: "new_task_available",
            task_id: taskId,
            task_type: (args as any).task_type,
            target_type: (args as any).target_type,
            timestamp: new Date().toISOString(),
          })
        );

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({ success: true, task_id: taskId, broadcast: true }),
            },
          ],
        };
      }

      case "ralph_get_status": {
        const result: any = {};

        if ((args as any).agent_id) {
          const agentData = await redis.hget("ralph:agents", (args as any).agent_id);
          if (agentData) {
            const agent = JSON.parse(agentData);
            const isAlive = await redis.exists(`ralph:heartbeats:${(args as any).agent_id}`);
            result.agent = { ...agent, is_alive: isAlive > 0 };
          }
        }

        if ((args as any).task_id) {
          const taskData = await redis.get(`ralph:tasks:data:${(args as any).task_id}`);
          if (taskData) {
            result.task = JSON.parse(taskData);
          }
        }

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(result, null, 2),
            },
          ],
        };
      }

      case "ralph_lock_file": {
        const { file_path, agent_id, ttl } = args as any;
        const lockKey = `ralph:locks:file:${file_path.replace(/[/\\]/g, ":")}`;

        const lockData = JSON.stringify({
          agent_id,
          file_path,
          acquired_at: new Date().toISOString(),
          ttl,
        });

        const acquired = await redis.set(lockKey, lockData, "EX", ttl || 300, "NX");

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({ success: !!acquired, file_path, agent_id }),
            },
          ],
        };
      }

      case "ralph_unlock_file": {
        const { file_path, agent_id } = args as any;
        const lockKey = `ralph:locks:file:${file_path.replace(/[/\\]/g, ":")}`;

        const existing = await redis.get(lockKey);
        if (existing) {
          const lock = JSON.parse(existing);
          if (lock.agent_id === agent_id) {
            await redis.del(lockKey);
            return {
              content: [{ type: "text", text: JSON.stringify({ success: true }) }],
            };
          }
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({ success: false, error: "Lock owned by different agent" }),
              },
            ],
          };
        }

        return {
          content: [{ type: "text", text: JSON.stringify({ success: true, note: "No lock existed" }) }],
        };
      }

      case "ralph_get_artifacts": {
        const artifacts: any[] = [];

        for await (const key of redis.scanStream({ match: "ralph:artifacts:*" })) {
          const data = await redis.hgetall(key as string);
          if (data) {
            if ((args as any).task_id && data.task_id !== (args as any).task_id) continue;
            if ((args as any).agent_id && data.agent_id !== (args as any).agent_id) continue;
            artifacts.push(data);
          }
        }

        return {
          content: [{ type: "text", text: JSON.stringify(artifacts, null, 2) }],
        };
      }

      case "ralph_send_message": {
        const { target_agent, message_type, payload } = args as any;

        const message = {
          type: message_type,
          from: "claude-code",
          timestamp: new Date().toISOString(),
          payload,
        };

        await redis.publish(`ralph:messages:${target_agent}`, JSON.stringify(message));

        return {
          content: [{ type: "text", text: JSON.stringify({ success: true, delivered_to: target_agent }) }],
        };
      }

      case "ralph_get_queue": {
        const { limit, status } = args as any;
        const taskIds = await redis.zrange("ralph:tasks:queue", 0, (limit || 20) - 1);

        const tasks = [];
        for (const id of taskIds) {
          const data = await redis.get(`ralph:tasks:data:${id}`);
          if (data) {
            const task = JSON.parse(data);
            if (!status || task.status === status) {
              tasks.push(task);
            }
          }
        }

        return {
          content: [{ type: "text", text: JSON.stringify(tasks, null, 2) }],
        };
      }

      case "ralph_cancel_task": {
        const { task_id } = args as any;
        const taskData = await redis.get(`ralph:tasks:data:${task_id}`);

        if (taskData) {
          const task = JSON.parse(taskData);
          task.status = "cancelled";
          task.cancelled_at = new Date().toISOString();
          await redis.set(`ralph:tasks:data:${task_id}`, JSON.stringify(task));
          await redis.zrem("ralph:tasks:queue", task_id);

          return {
            content: [{ type: "text", text: JSON.stringify({ success: true, task_id }) }],
          };
        }

        return {
          content: [{ type: "text", text: JSON.stringify({ success: false, error: "Task not found" }) }],
        };
      }

      case "ralph_validate_deps": {
        const { task_id, dependencies } = args as any;
        const validation = await validateDependencies(task_id, dependencies);

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({
                valid: validation.valid,
                task_id,
                dependencies,
                error: validation.error,
                cycle: validation.cycle,
              }),
            },
          ],
        };
      }

      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error: any) {
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify({ error: error.message }),
        },
      ],
      isError: true,
    };
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("Ralph MCP Server running on stdio");
}

main().catch(console.error);
