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
 *
 * Librarian documentation search tools:
 * - librarian_search: Search indexed documentation
 * - librarian_list_sources: List available documentation sources
 * - librarian_get_document: Retrieve specific document by ID
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
import { spawn } from "child_process";
import * as path from "path";

const REDIS_URL = process.env.REDIS_URL || "redis://localhost:6379";
const LIBRARIAN_PATH = process.env.LIBRARIAN_PATH || "librarian";
const LIBRARIAN_TIMEOUT = parseInt(process.env.LIBRARIAN_TIMEOUT || "60000", 10);

let redis: Redis;

function sanitizeLibrarianArg(arg: string): string {
  if (/[;&|`$(){}[\]<>\\'\"\n\r]/.test(arg)) {
    throw new Error(`Invalid characters in librarian argument`);
  }
  if (arg.length > 1000) {
    throw new Error('Argument too long');
  }
  return arg;
}

function validateFilePath(filePath: string): string {
  const normalized = filePath.replace(/\\/g, '/');
  if (normalized.includes('..')) {
    throw new Error('Path traversal detected');
  }
  if (!/^[\w\-./]+$/.test(normalized)) {
    throw new Error('Invalid characters in file path');
  }
  return normalized;
}

// =============================================================================
// Librarian CLI Integration
// =============================================================================

interface LibrarianSearchResult {
  title: string;
  content: string;
  source: string;
  library: string;
  url?: string;
  score: number;
  metadata?: Record<string, any>;
}

interface LibrarianSource {
  name: string;
  source_url: string;
  docs_path: string;
  ref: string;
  last_indexed?: string;
  doc_count: number;
  status: string;
}

async function runLibrarianCommand(
  args: string[],
  timeout: number = LIBRARIAN_TIMEOUT
): Promise<{ stdout: string; stderr: string; exitCode: number }> {
  const sanitizedArgs = args.map(sanitizeLibrarianArg);

  return new Promise((resolve, reject) => {
    const proc = spawn(LIBRARIAN_PATH, sanitizedArgs, {
      timeout,
      shell: false,
      windowsHide: true,
    });

    let stdout = "";
    let stderr = "";
    let settled = false;

    const timeoutId = setTimeout(() => {
      if (!settled) {
        settled = true;
        proc.kill();
        reject(new Error(`Librarian command timed out after ${timeout}ms`));
      }
    }, timeout);

    proc.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    proc.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    proc.on("close", (code) => {
      if (!settled) {
        settled = true;
        clearTimeout(timeoutId);
        resolve({ stdout, stderr, exitCode: code || 0 });
      }
    });

    proc.on("error", (err) => {
      if (!settled) {
        settled = true;
        clearTimeout(timeoutId);
        reject(err);
      }
    });
  });
}

async function librarianSearch(
  query: string,
  options: {
    library?: string;
    mode?: "word" | "vector" | "hybrid";
    limit?: number;
  } = {}
): Promise<LibrarianSearchResult[]> {
  if (!options.library) {
    throw new Error("Library name is required for search. Use librarian_list_sources to see available libraries.");
  }

  const args = ["search", "--library", options.library, query];
  args.push("--mode", options.mode || "hybrid");

  const result = await runLibrarianCommand(args);

  if (result.exitCode !== 0) {
    const errMsg = result.stderr || result.stdout;
    throw new Error(`Librarian search failed: ${errMsg}`);
  }

  return parseTextResults(result.stdout, options.library);
}

function parseTextResults(output: string, library?: string): LibrarianSearchResult[] {
  const results: LibrarianSearchResult[] = [];
  const lines = output.split("\n");

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("-") === false) continue;
    if (trimmed.includes("use `librarian get")) continue;

    const match = trimmed.match(/^-\s+([^:]+):\s+([^\s]+)\s+\(([^)]+)\)\s+doc\s+(\d+)\s+slice\s+([^\s]+)\s+score\s+([\d.]+)/);
    if (match) {
      results.push({
        title: match[2],
        content: "",
        source: match[3],
        library: match[1] || library || "unknown",
        score: parseFloat(match[6]) || 0,
        metadata: {
          doc_id: match[4],
          slice: match[5],
        },
      });
    } else {
      const simpleMatch = trimmed.match(/^-\s+(.+)$/);
      if (simpleMatch) {
        results.push({
          title: simpleMatch[1],
          content: "",
          source: "",
          library: library || "unknown",
          score: 0,
        });
      }
    }
  }

  return results;
}

async function librarianListSources(): Promise<LibrarianSource[]> {
  const statusResult = await runLibrarianCommand(["status"]);
  const sources: LibrarianSource[] = [];

  const sourceCountMatch = statusResult.stdout.match(/Sources:\s*(\d+)/);
  const totalSources = sourceCountMatch ? parseInt(sourceCountMatch[1], 10) : 0;

  const commonLibs = [
    "react", "next", "vue", "angular", "svelte", "typescript",
    "node", "express", "fastify", "prisma", "drizzle", "tailwind",
    "zod", "trpc", "remix", "astro", "vite", "esbuild"
  ];

  for (const lib of commonLibs) {
    try {
      const result = await runLibrarianCommand(["library", lib], 10000);
      if (result.exitCode === 0 && result.stdout.trim()) {
        const lines = result.stdout.split("\n");
        for (const line of lines) {
          const match = line.match(/^-\s+([^\s]+)\s+\(ref:\s*([^,]+),\s*versions?:\s*([^)]+)\)/);
          if (match) {
            sources.push({
              name: match[1],
              source_url: `https://github.com/${match[1]}`,
              docs_path: "",
              ref: match[2].trim(),
              doc_count: 0,
              status: "indexed",
            });
          }
        }
      }
    } catch (e) {
    }
  }

  const uniqueSources = Array.from(new Map(sources.map(s => [s.name, s])).values());

  return uniqueSources.length > 0 ? uniqueSources : [{
    name: "Use 'librarian library <name>' to find specific libraries",
    source_url: "",
    docs_path: "",
    ref: "",
    doc_count: totalSources,
    status: "hint",
  }];
}

async function librarianGetDocument(
  library: string,
  docId: string,
  slice?: string
): Promise<Record<string, any> | null> {
  const args = ["get", "--library", library, "--doc", docId];
  if (slice) {
    args.push("--slice", slice);
  }

  const result = await runLibrarianCommand(args);

  if (result.exitCode !== 0) {
    return null;
  }

  return {
    library,
    doc_id: docId,
    slice: slice || "full",
    content: result.stdout,
  };
}

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

async function createRedisClient(url: string, maxRetries = 5): Promise<Redis> {
  let lastError: Error | null = null;

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const client = new Redis(url, {
        retryStrategy(times) {
          const delay = Math.min(times * 100, 3000);
          console.error(`Redis reconnecting, attempt ${times}, delay ${delay}ms`);
          return delay;
        },
        maxRetriesPerRequest: 3,
        reconnectOnError(err) {
          return err.message.includes('READONLY');
        },
        lazyConnect: true,
        connectTimeout: 10000,
      });

      await client.connect();
      await client.ping();
      console.error(`Redis connected to ${url}`);

      client.on('error', (err) => console.error('Redis error:', err));
      client.on('reconnecting', () => console.error('Reconnecting to Redis...'));

      return client;
    } catch (err: any) {
      lastError = err;
      const delay = Math.min(1000 * Math.pow(2, attempt), 30000);
      console.error(
        `Redis connection failed (attempt ${attempt + 1}/${maxRetries}): ${err.message}`
      );

      if (attempt < maxRetries - 1) {
        console.error(`Retrying in ${delay}ms...`);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }

  throw new Error(
    `Failed to connect to Redis at ${url} after ${maxRetries} attempts: ${lastError?.message}`
  );
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

  // Librarian documentation search tools
  librarian_search: z.object({
    query: z.string().describe("Search query (natural language)"),
    library: z.string().optional().describe("Filter to specific library/source"),
    mode: z.enum(["word", "vector", "hybrid"]).default("hybrid").describe("Search mode"),
    limit: z.number().min(1).max(50).default(10).describe("Maximum results"),
  }),

  librarian_list_sources: z.object({}),

  librarian_get_document: z.object({
    library: z.string().describe("Library name (e.g., reactjs/react.dev)"),
    doc_id: z.string().describe("Document ID from search results"),
    slice: z.string().optional().describe("Slice range (e.g., '13:29') from search results"),
  }),

  librarian_search_api: z.object({
    api_name: z.string().describe("API/function/class name to search"),
    library: z.string().describe("Library to search in"),
  }),

  librarian_search_error: z.object({
    error_message: z.string().describe("Error message to search solutions for"),
    library: z.string().optional().describe("Library context"),
  }),

  librarian_find_library: z.object({
    name: z.string().describe("Library name to search for (e.g., react, next, prisma)"),
  }),

  // Memory MCP tools - persistent context across agents
  ralph_memory_store: z.object({
    content: z.string().describe("Memory content to store"),
    category: z.enum(["architecture", "pattern", "blocker", "decision", "learning", "general"]).default("general"),
    tags: z.array(z.string()).optional().describe("Tags for categorization"),
    task_id: z.string().optional().describe("Associated task ID"),
    project_id: z.string().optional().describe("Project ID (defaults to RALPH_PROJECT_ID env)"),
  }),

  ralph_memory_recall: z.object({
    query: z.string().describe("Search query for memories"),
    category: z.string().optional().describe("Filter by category"),
    task_id: z.string().optional().describe("Filter by task ID"),
    limit: z.number().default(10).describe("Maximum results to return"),
    project_id: z.string().optional().describe("Project ID (defaults to RALPH_PROJECT_ID env)"),
  }),

  ralph_memory_context: z.object({
    task_id: z.string().optional().describe("Get task-specific context"),
    project_id: z.string().optional().describe("Project ID (defaults to RALPH_PROJECT_ID env)"),
  }),

  ralph_memory_handoff: z.object({
    task_id: z.string().describe("Task being handed off"),
    summary: z.string().describe("Summary of work completed"),
    next_steps: z.array(z.string()).describe("Recommended next steps"),
    blockers: z.array(z.string()).optional().describe("Any blockers encountered"),
    project_id: z.string().optional().describe("Project ID (defaults to RALPH_PROJECT_ID env)"),
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
      // Librarian documentation search tools
      {
        name: "librarian_search",
        description: "Search indexed documentation using keyword, semantic, or hybrid search. Returns relevant documentation chunks with scores.",
        inputSchema: {
          type: "object",
          properties: {
            query: { type: "string", description: "Search query (natural language)" },
            library: { type: "string", description: "Filter to specific library/source (optional)" },
            mode: {
              type: "string",
              enum: ["word", "vector", "hybrid"],
              default: "hybrid",
              description: "Search mode: word (keyword), vector (semantic), hybrid (combined)"
            },
            limit: { type: "number", minimum: 1, maximum: 50, default: 10, description: "Maximum results" },
          },
          required: ["query"],
        },
      },
      {
        name: "librarian_list_sources",
        description: "List all available documentation sources indexed in Librarian",
        inputSchema: {
          type: "object",
          properties: {},
          required: [],
        },
      },
      {
        name: "librarian_get_document",
        description: "Retrieve a specific document chunk by its ID and slice from a library. Use the doc_id and slice from search results.",
        inputSchema: {
          type: "object",
          properties: {
            library: { type: "string", description: "Library name (e.g., reactjs/react.dev)" },
            doc_id: { type: "string", description: "Document ID from search results" },
            slice: { type: "string", description: "Slice range from search results (e.g., '13:29')" },
          },
          required: ["library", "doc_id"],
        },
      },
      {
        name: "librarian_search_api",
        description: "Search for API documentation (functions, classes, methods) in a specific library",
        inputSchema: {
          type: "object",
          properties: {
            api_name: { type: "string", description: "API/function/class name to search" },
            library: { type: "string", description: "Library to search in" },
          },
          required: ["api_name", "library"],
        },
      },
      {
        name: "librarian_search_error",
        description: "Search for error message solutions and troubleshooting information",
        inputSchema: {
          type: "object",
          properties: {
            error_message: { type: "string", description: "Error message to search solutions for" },
            library: { type: "string", description: "Library context (optional)" },
          },
          required: ["error_message"],
        },
      },
      {
        name: "librarian_find_library",
        description: "Find the full library name/ID for searching. Use this to discover the correct library identifier before calling librarian_search.",
        inputSchema: {
          type: "object",
          properties: {
            name: { type: "string", description: "Library name to search for (e.g., react, next, prisma)" },
          },
          required: ["name"],
        },
      },
      // Memory MCP tools
      {
        name: "ralph_memory_store",
        description: "Store a memory for future recall. Use for architecture decisions, patterns discovered, blockers, and learnings.",
        inputSchema: {
          type: "object",
          properties: {
            content: { type: "string", description: "Memory content to store" },
            category: {
              type: "string",
              enum: ["architecture", "pattern", "blocker", "decision", "learning", "general"],
              default: "general",
            },
            tags: { type: "array", items: { type: "string" }, description: "Tags for categorization" },
            task_id: { type: "string", description: "Associated task ID" },
            project_id: { type: "string", description: "Project ID (defaults to env)" },
          },
          required: ["content"],
        },
      },
      {
        name: "ralph_memory_recall",
        description: "Search memories by query. Returns relevant memories for context loading.",
        inputSchema: {
          type: "object",
          properties: {
            query: { type: "string", description: "Search query for memories" },
            category: { type: "string", description: "Filter by category" },
            task_id: { type: "string", description: "Filter by task ID" },
            limit: { type: "number", default: 10, description: "Maximum results" },
            project_id: { type: "string", description: "Project ID (defaults to env)" },
          },
          required: ["query"],
        },
      },
      {
        name: "ralph_memory_context",
        description: "Get accumulated project or task context. Load this before starting work.",
        inputSchema: {
          type: "object",
          properties: {
            task_id: { type: "string", description: "Get task-specific context" },
            project_id: { type: "string", description: "Project ID (defaults to env)" },
          },
        },
      },
      {
        name: "ralph_memory_handoff",
        description: "Leave notes for the next agent. Use when completing a task to preserve context.",
        inputSchema: {
          type: "object",
          properties: {
            task_id: { type: "string", description: "Task being handed off" },
            summary: { type: "string", description: "Summary of work completed" },
            next_steps: { type: "array", items: { type: "string" }, description: "Recommended next steps" },
            blockers: { type: "array", items: { type: "string" }, description: "Any blockers encountered" },
            project_id: { type: "string", description: "Project ID (defaults to env)" },
          },
          required: ["task_id", "summary", "next_steps"],
        },
      },
    ],
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    // Validate args against schema if one exists
    const schema = TOOLS[name];
    const validatedArgs = schema ? schema.parse(args) : args;

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
        const dependencies = (validatedArgs as any).dependencies || [];

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
          ...validatedArgs,
          deps: dependencies,
          status: "pending",
          created_at: new Date().toISOString(),
          created_by: "claude-code",
        };

        await redis.set(`ralph:tasks:data:${taskId}`, JSON.stringify(task));

        const priority = (validatedArgs as any).priority || 5;
        const score = (10 - priority) * 1000000 + Date.now();
        await redis.zadd("ralph:tasks:queue", score, taskId);

        await redis.publish(
          `ralph:messages:${(validatedArgs as any).agent_id}`,
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
          ...validatedArgs,
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
            task_type: (validatedArgs as any).task_type,
            target_type: (validatedArgs as any).target_type,
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

        if ((validatedArgs as any).agent_id) {
          const agentData = await redis.hget("ralph:agents", (validatedArgs as any).agent_id);
          if (agentData) {
            const agent = JSON.parse(agentData);
            const isAlive = await redis.exists(`ralph:heartbeats:${(validatedArgs as any).agent_id}`);
            result.agent = { ...agent, is_alive: isAlive > 0 };
          }
        }

        if ((validatedArgs as any).task_id) {
          const taskData = await redis.get(`ralph:tasks:data:${(validatedArgs as any).task_id}`);
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
        const { file_path, agent_id, ttl } = validatedArgs as any;
        const validatedPath = validateFilePath(file_path);
        const lockKey = `ralph:locks:file:${validatedPath.replace(/[/\\]/g, ":")}`;

        const lockData = JSON.stringify({
          agent_id,
          file_path: validatedPath,
          acquired_at: new Date().toISOString(),
          ttl,
        });

        const acquired = await redis.set(lockKey, lockData, "EX", ttl || 300, "NX");

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({ success: !!acquired, file_path: validatedPath, agent_id }),
            },
          ],
        };
      }

      case "ralph_unlock_file": {
        const { file_path, agent_id } = validatedArgs as any;
        const validatedPath = validateFilePath(file_path);
        const lockKey = `ralph:locks:file:${validatedPath.replace(/[/\\]/g, ":")}`;

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
            if ((validatedArgs as any).task_id && data.task_id !== (validatedArgs as any).task_id) continue;
            if ((validatedArgs as any).agent_id && data.agent_id !== (validatedArgs as any).agent_id) continue;
            artifacts.push(data);
          }
        }

        return {
          content: [{ type: "text", text: JSON.stringify(artifacts, null, 2) }],
        };
      }

      case "ralph_send_message": {
        const { target_agent, message_type, payload } = validatedArgs as any;

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
        const { limit, status } = validatedArgs as any;
        const taskIds = await redis.zrange("ralph:tasks:queue", 0, (limit || 20) - 1);

        if (taskIds.length === 0) {
          return { content: [{ type: "text", text: "[]" }] };
        }

        const keys = taskIds.map((id) => `ralph:tasks:data:${id}`);
        const results = await redis.mget(...keys);

        const tasks = results
          .filter((data): data is string => data !== null)
          .map((data) => JSON.parse(data))
          .filter((task) => !status || task.status === status);

        return {
          content: [{ type: "text", text: JSON.stringify(tasks, null, 2) }],
        };
      }

      case "ralph_cancel_task": {
        const { task_id } = validatedArgs as any;
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
        const { task_id, dependencies } = validatedArgs as any;
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

      // =======================================================================
      // Librarian Documentation Search Tools
      // =======================================================================

      case "librarian_search": {
        if (!librarianAvailable) {
          return {
            content: [{
              type: "text",
              text: JSON.stringify({
                success: false,
                error: "Librarian is not available. Install with: npm install -g @iannuttall/librarian",
                hint: "Set LIBRARIAN_PATH environment variable if installed in a custom location"
              })
            }],
            isError: true
          };
        }

        const { query, library, mode, limit } = validatedArgs as any;

        try {
          const results = await librarianSearch(query, {
            library,
            mode: mode || "hybrid",
            limit: limit || 10,
          });

          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({
                  success: true,
                  query,
                  mode: mode || "hybrid",
                  library: library || "all",
                  result_count: results.length,
                  results: results.map((r) => ({
                    title: r.title,
                    library: r.library,
                    source: r.source,
                    score: r.score,
                    content: r.content.substring(0, 500) + (r.content.length > 500 ? "..." : ""),
                    url: r.url,
                  })),
                }, null, 2),
              },
            ],
          };
        } catch (err: any) {
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({ success: false, error: err.message }),
              },
            ],
            isError: true,
          };
        }
      }

      case "librarian_list_sources": {
        if (!librarianAvailable) {
          return {
            content: [{
              type: "text",
              text: JSON.stringify({
                success: false,
                error: "Librarian is not available. Install with: npm install -g @iannuttall/librarian",
                hint: "Set LIBRARIAN_PATH environment variable if installed in a custom location"
              })
            }],
            isError: true
          };
        }

        try {
          const sources = await librarianListSources();

          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({
                  success: true,
                  source_count: sources.length,
                  sources: sources.map((s) => ({
                    name: s.name,
                    doc_count: s.doc_count,
                    status: s.status,
                    source_url: s.source_url,
                    last_indexed: s.last_indexed,
                  })),
                }, null, 2),
              },
            ],
          };
        } catch (err: any) {
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({ success: false, error: err.message }),
              },
            ],
            isError: true,
          };
        }
      }

      case "librarian_get_document": {
        if (!librarianAvailable) {
          return {
            content: [{
              type: "text",
              text: JSON.stringify({
                success: false,
                error: "Librarian is not available. Install with: npm install -g @iannuttall/librarian",
                hint: "Set LIBRARIAN_PATH environment variable if installed in a custom location"
              })
            }],
            isError: true
          };
        }

        const { library, doc_id, slice } = validatedArgs as any;

        try {
          const doc = await librarianGetDocument(library, doc_id, slice);

          if (!doc) {
            return {
              content: [
                {
                  type: "text",
                  text: JSON.stringify({ success: false, error: "Document not found" }),
                },
              ],
            };
          }

          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({
                  success: true,
                  library,
                  doc_id,
                  slice: slice || "full",
                  document: doc,
                }, null, 2),
              },
            ],
          };
        } catch (err: any) {
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({ success: false, error: err.message }),
              },
            ],
            isError: true,
          };
        }
      }

      case "librarian_search_api": {
        if (!librarianAvailable) {
          return {
            content: [{
              type: "text",
              text: JSON.stringify({
                success: false,
                error: "Librarian is not available. Install with: npm install -g @iannuttall/librarian",
                hint: "Set LIBRARIAN_PATH environment variable if installed in a custom location"
              })
            }],
            isError: true
          };
        }

        const { api_name, library } = validatedArgs as any;

        try {
          const query = `${api_name} API reference usage example`;
          const results = await librarianSearch(query, {
            library,
            mode: "hybrid",
            limit: 5,
          });

          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({
                  success: true,
                  api_name,
                  library,
                  result_count: results.length,
                  results: results.map((r) => ({
                    title: r.title,
                    source: r.source,
                    score: r.score,
                    content: r.content,
                    url: r.url,
                  })),
                }, null, 2),
              },
            ],
          };
        } catch (err: any) {
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({ success: false, error: err.message }),
              },
            ],
            isError: true,
          };
        }
      }

      case "librarian_search_error": {
        if (!librarianAvailable) {
          return {
            content: [{
              type: "text",
              text: JSON.stringify({
                success: false,
                error: "Librarian is not available. Install with: npm install -g @iannuttall/librarian",
                hint: "Set LIBRARIAN_PATH environment variable if installed in a custom location"
              })
            }],
            isError: true
          };
        }

        const { error_message, library } = validatedArgs as any;

        try {
          const query = `error ${error_message} solution fix troubleshooting`;
          const results = await librarianSearch(query, {
            library,
            mode: "hybrid",
            limit: 10,
          });

          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({
                  success: true,
                  error_message,
                  library: library || "all",
                  result_count: results.length,
                  results: results.map((r) => ({
                    title: r.title,
                    library: r.library,
                    source: r.source,
                    score: r.score,
                    content: r.content,
                    url: r.url,
                  })),
                }, null, 2),
              },
            ],
          };
        } catch (err: any) {
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({ success: false, error: err.message }),
              },
            ],
            isError: true,
          };
        }
      }

      case "librarian_find_library": {
        if (!librarianAvailable) {
          return {
            content: [{
              type: "text",
              text: JSON.stringify({
                success: false,
                error: "Librarian is not available. Install with: npm install -g @iannuttall/librarian",
                hint: "Set LIBRARIAN_PATH environment variable if installed in a custom location"
              })
            }],
            isError: true
          };
        }

        const { name: libName } = validatedArgs as any;

        try {
          const result = await runLibrarianCommand(["library", libName], 15000);

          if (result.exitCode !== 0 || !result.stdout.trim()) {
            return {
              content: [
                {
                  type: "text",
                  text: JSON.stringify({
                    success: false,
                    query: libName,
                    message: "No matching libraries found. Try a different name or add the library with 'librarian add <url>'",
                  }),
                },
              ],
            };
          }

          const libraries: Array<{ name: string; ref: string; versions: string }> = [];
          const lines = result.stdout.split("\n");

          for (const line of lines) {
            const match = line.match(/^-\s+([^\s]+)\s+\(ref:\s*([^,]+),\s*versions?:\s*([^)]+)\)/);
            if (match) {
              libraries.push({
                name: match[1],
                ref: match[2].trim(),
                versions: match[3].trim(),
              });
            }
          }

          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({
                  success: true,
                  query: libName,
                  libraries,
                  usage_hint: "Use the 'name' value as the 'library' parameter in librarian_search",
                }, null, 2),
              },
            ],
          };
        } catch (err: any) {
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify({ success: false, error: err.message }),
              },
            ],
            isError: true,
          };
        }
      }

      // =======================================================================
      // Memory MCP Tools - Persistent Context Across Agents
      // =======================================================================

      case "ralph_memory_store": {
        const { content, category, tags, task_id, project_id } = validatedArgs as any;
        const projId = project_id || process.env.RALPH_PROJECT_ID || "default";
        const memoryId = `mem-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;

        const memory = {
          id: memoryId,
          content,
          category: category || "general",
          tags: tags || [],
          task_id: task_id || null,
          created_at: new Date().toISOString(),
          agent_id: "claude-code",
        };

        await redis.hset(`claude_mem:${projId}:memories`, memoryId, JSON.stringify(memory));

        if (task_id) {
          await redis.sadd(`claude_mem:${projId}:task:${task_id}:memories`, memoryId);
        }

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({ success: true, memory_id: memoryId, project_id: projId }),
            },
          ],
        };
      }

      case "ralph_memory_recall": {
        const { query, category, task_id, limit, project_id } = validatedArgs as any;
        const projId = project_id || process.env.RALPH_PROJECT_ID || "default";
        const maxResults = limit || 10;

        const allMemories = await redis.hgetall(`claude_mem:${projId}:memories`);
        const memories: any[] = [];

        const queryLower = query.toLowerCase();
        const queryWords = queryLower.split(/\s+/);

        for (const [id, data] of Object.entries(allMemories)) {
          const mem = JSON.parse(data);

          if (category && mem.category !== category) continue;
          if (task_id && mem.task_id !== task_id) continue;

          const contentLower = mem.content.toLowerCase();
          const tagMatch = mem.tags?.some((t: string) => queryWords.some((w: string) => t.toLowerCase().includes(w)));
          const contentMatch = queryWords.some((w: string) => contentLower.includes(w));

          if (tagMatch || contentMatch) {
            const matchScore = queryWords.filter((w: string) => contentLower.includes(w)).length;
            memories.push({ ...mem, score: matchScore + (tagMatch ? 2 : 0) });
          }
        }

        memories.sort((a, b) => b.score - a.score);
        const results = memories.slice(0, maxResults);

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({
                success: true,
                query,
                project_id: projId,
                result_count: results.length,
                memories: results,
              }, null, 2),
            },
          ],
        };
      }

      case "ralph_memory_context": {
        const { task_id, project_id } = validatedArgs as any;
        const projId = project_id || process.env.RALPH_PROJECT_ID || "default";

        const projectContext = await redis.hgetall(`claude_mem:${projId}:project_context`);
        let taskContext = {};
        let taskMemories: any[] = [];

        if (task_id) {
          taskContext = await redis.hgetall(`claude_mem:${projId}:task:${task_id}`) || {};

          const handoffData = await redis.get(`claude_mem:${projId}:handoffs:${task_id}`);
          if (handoffData) {
            taskContext = { ...taskContext, handoff: JSON.parse(handoffData) };
          }

          const memoryIds = await redis.smembers(`claude_mem:${projId}:task:${task_id}:memories`);
          if (memoryIds.length > 0) {
            const allMem = await redis.hgetall(`claude_mem:${projId}:memories`);
            taskMemories = memoryIds
              .filter((id) => allMem[id])
              .map((id) => JSON.parse(allMem[id]));
          }
        }

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({
                success: true,
                project_id: projId,
                project_context: projectContext,
                task_id: task_id || null,
                task_context: taskContext,
                task_memories: taskMemories,
              }, null, 2),
            },
          ],
        };
      }

      case "ralph_memory_handoff": {
        const { task_id, summary, next_steps, blockers, project_id } = validatedArgs as any;
        const projId = project_id || process.env.RALPH_PROJECT_ID || "default";

        const handoff = {
          task_id,
          summary,
          next_steps: next_steps || [],
          blockers: blockers || [],
          handed_off_at: new Date().toISOString(),
          handed_off_by: "claude-code",
        };

        await redis.set(`claude_mem:${projId}:handoffs:${task_id}`, JSON.stringify(handoff));

        await redis.hset(`claude_mem:${projId}:task:${task_id}`, {
          status: "handed_off",
          summary,
          handed_off_at: handoff.handed_off_at,
        });

        const learningMemory = {
          id: `learn-${task_id}`,
          content: `Task ${task_id}: ${summary}. Next: ${next_steps.join(", ")}`,
          category: "learning",
          tags: ["handoff", task_id],
          task_id,
          created_at: handoff.handed_off_at,
          agent_id: "claude-code",
        };
        await redis.hset(`claude_mem:${projId}:memories`, learningMemory.id, JSON.stringify(learningMemory));

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({
                success: true,
                task_id,
                project_id: projId,
                handoff_stored: true,
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

let librarianAvailable = false;

async function checkLibrarianAvailability(): Promise<boolean> {
  try {
    const result = await runLibrarianCommand(["--version"], 10000);
    if (result.exitCode === 0) {
      const version = result.stdout.trim().split("\n")[0];
      console.error(`Librarian available: ${version}`);
      return true;
    }
    console.error(`Librarian check failed with exit code ${result.exitCode}`);
    return false;
  } catch (err: any) {
    if (err.code === "ENOENT") {
      console.error(`Librarian not found at path: ${LIBRARIAN_PATH}`);
    } else {
      console.error(`Librarian unavailable: ${err.message}`);
    }
    return false;
  }
}

async function main() {
  try {
    redis = await createRedisClient(REDIS_URL);
  } catch (err: any) {
    console.error(`FATAL: ${err.message}`);
    process.exit(1);
  }

  librarianAvailable = await checkLibrarianAvailability();
  if (!librarianAvailable) {
    console.error(
      "WARNING: Librarian unavailable. Documentation search tools will return errors. " +
      "Install with: npm install -g @iannuttall/librarian"
    );
  }

  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("Ralph MCP Server running on stdio");
}

main().catch(console.error);
