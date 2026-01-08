import Redis from 'ioredis-mock';

export type MockRedis = InstanceType<typeof Redis>;

export function createMockRedis(): MockRedis {
  return new Redis();
}

export interface TaskData {
  id: string;
  title: string;
  description: string;
  status: string;
  priority: number;
  agent_type: string;
  dependencies: string[];
  wait_for: string[];
  created_at: number;
  task_type?: string;
  files?: string[];
  acceptance_criteria?: string[];
  assigned_to?: string;
}

export interface AgentData {
  id: string;
  type: string;
  status: string;
  capabilities?: string[];
  current_task?: string;
}

export async function createTestTask(
  redis: MockRedis,
  taskId: string,
  data: Partial<TaskData> = {}
): Promise<TaskData> {
  const task: TaskData = {
    id: taskId,
    title: data.title || 'Test Task',
    description: data.description || 'Test description',
    status: data.status || 'pending',
    priority: data.priority ?? 5,
    agent_type: data.agent_type || 'general',
    dependencies: data.dependencies || [],
    wait_for: data.wait_for || [],
    created_at: data.created_at || Date.now(),
    task_type: data.task_type || 'implement',
    files: data.files || [],
    acceptance_criteria: data.acceptance_criteria || [],
    assigned_to: data.assigned_to,
  };

  await redis.set(`ralph:tasks:data:${taskId}`, JSON.stringify(task));
  await redis.zadd('ralph:tasks:queue', task.priority.toString(), taskId);

  return task;
}

export async function createTestAgent(
  redis: MockRedis,
  agentId: string,
  data: Partial<AgentData> & { alive?: boolean } = {}
): Promise<AgentData> {
  const agent: AgentData = {
    id: agentId,
    type: data.type || 'general',
    status: data.status || 'idle',
    capabilities: data.capabilities || ['implement', 'debug'],
    current_task: data.current_task,
  };

  await redis.hset('ralph:agents', agentId, JSON.stringify(agent));

  if (data.alive !== false) {
    await redis.setex(`ralph:heartbeats:${agentId}`, 30, Date.now().toString());
  }

  return agent;
}

export async function createFileLock(
  redis: MockRedis,
  filePath: string,
  agentId: string,
  ttl: number = 300
): Promise<{ agent_id: string; file_path: string; acquired_at: string }> {
  const normalizedPath = filePath.replace(/[/\\]/g, ':');
  const lockKey = `ralph:locks:file:${normalizedPath}`;
  const lockData = {
    agent_id: agentId,
    file_path: filePath,
    acquired_at: new Date().toISOString(),
    ttl,
  };

  await redis.set(lockKey, JSON.stringify(lockData), 'EX', ttl);

  return lockData;
}

export async function getTaskFromRedis(
  redis: MockRedis,
  taskId: string
): Promise<TaskData | null> {
  const data = await redis.get(`ralph:tasks:data:${taskId}`);
  if (!data) return null;
  return JSON.parse(data);
}

export async function getAgentFromRedis(
  redis: MockRedis,
  agentId: string
): Promise<AgentData | null> {
  const data = await redis.hget('ralph:agents', agentId);
  if (!data) return null;
  return JSON.parse(data);
}

export function generateTaskId(): string {
  return `task-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function generateAgentId(): string {
  return `agent-${Math.random().toString(36).slice(2, 10)}`;
}
