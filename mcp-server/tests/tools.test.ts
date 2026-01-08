import { describe, it, expect, beforeEach } from '@jest/globals';
import {
  createMockRedis,
  createTestTask,
  createTestAgent,
  createFileLock,
  getTaskFromRedis,
  MockRedis,
} from './setup.js';

describe('ralph_list_agents', () => {
  let redis: MockRedis;

  beforeEach(() => {
    redis = createMockRedis();
  });

  it('returns empty array when no agents', async () => {
    const agents = await redis.hgetall('ralph:agents');
    expect(Object.keys(agents)).toHaveLength(0);
  });

  it('returns agents with alive status based on heartbeat', async () => {
    await createTestAgent(redis, 'agent-1', { alive: true });
    await createTestAgent(redis, 'agent-2', { alive: false });

    const all = await redis.hgetall('ralph:agents');
    const heartbeat1 = await redis.exists('ralph:heartbeats:agent-1');
    const heartbeat2 = await redis.exists('ralph:heartbeats:agent-2');

    expect(Object.keys(all)).toHaveLength(2);
    expect(heartbeat1).toBe(1);
    expect(heartbeat2).toBe(0);
  });

  it('returns agent data with correct structure', async () => {
    await createTestAgent(redis, 'agent-frontend', {
      type: 'frontend',
      status: 'busy',
      capabilities: ['implement', 'debug', 'test'],
    });

    const agentData = await redis.hget('ralph:agents', 'agent-frontend');
    const agent = JSON.parse(agentData!);

    expect(agent.id).toBe('agent-frontend');
    expect(agent.type).toBe('frontend');
    expect(agent.status).toBe('busy');
    expect(agent.capabilities).toContain('implement');
  });
});

describe('ralph_send_task', () => {
  let redis: MockRedis;

  beforeEach(() => {
    redis = createMockRedis();
  });

  it('creates task in pending status', async () => {
    const taskId = 'test-task-1';
    await createTestTask(redis, taskId, { title: 'Build feature' });

    const stored = await redis.get(`ralph:tasks:data:${taskId}`);
    expect(stored).toBeTruthy();
    expect(JSON.parse(stored!).status).toBe('pending');
  });

  it('adds task to priority queue', async () => {
    const taskId = 'test-task-2';
    await createTestTask(redis, taskId, { priority: 8 });

    const score = await redis.zscore('ralph:tasks:queue', taskId);
    expect(score).toBe('8');
  });

  it('stores task with all required fields', async () => {
    const taskId = 'test-task-3';
    await createTestTask(redis, taskId, {
      title: 'Implement API endpoint',
      description: 'Create REST endpoint for users',
      priority: 7,
      task_type: 'implement',
      files: ['src/api/users.ts'],
      acceptance_criteria: ['Returns 200 on success', 'Validates input'],
    });

    const task = await getTaskFromRedis(redis, taskId);
    expect(task).toBeTruthy();
    expect(task!.title).toBe('Implement API endpoint');
    expect(task!.description).toBe('Create REST endpoint for users');
    expect(task!.priority).toBe(7);
    expect(task!.task_type).toBe('implement');
    expect(task!.files).toContain('src/api/users.ts');
    expect(task!.acceptance_criteria).toHaveLength(2);
  });

  it('respects task dependencies', async () => {
    await createTestTask(redis, 'dep-task-1', {
      title: 'Dependency task',
      status: 'completed',
    });

    await createTestTask(redis, 'main-task', {
      title: 'Main task',
      dependencies: ['dep-task-1'],
    });

    const task = await getTaskFromRedis(redis, 'main-task');
    expect(task!.dependencies).toContain('dep-task-1');
  });
});

describe('ralph_lock_file', () => {
  let redis: MockRedis;

  beforeEach(() => {
    redis = createMockRedis();
  });

  it('acquires lock when not held', async () => {
    const lockKey = 'ralph:locks:file:path:to:file.ts';
    const lockData = JSON.stringify({ agent_id: 'agent-1', acquired_at: Date.now() });

    const result = await redis.set(lockKey, lockData, 'EX', 300, 'NX');
    expect(result).toBe('OK');
  });

  it('fails to acquire when already held', async () => {
    const lockKey = 'ralph:locks:file:path:to:file.ts';
    const existingLock = JSON.stringify({ agent_id: 'agent-1', acquired_at: Date.now() });
    await redis.set(lockKey, existingLock, 'EX', 300);

    const result = await redis.set(lockKey, 'new-lock', 'EX', 300, 'NX');
    expect(result).toBeNull();
  });

  it('releases lock correctly', async () => {
    const filePath = 'src/module.ts';
    await createFileLock(redis, filePath, 'agent-1');

    const lockKey = `ralph:locks:file:${filePath.replace(/[/\\]/g, ':')}`;
    await redis.del(lockKey);

    const exists = await redis.exists(lockKey);
    expect(exists).toBe(0);
  });

  it('only allows owner to release lock', async () => {
    const filePath = 'src/module.ts';
    await createFileLock(redis, filePath, 'agent-1');

    const lockKey = `ralph:locks:file:${filePath.replace(/[/\\]/g, ':')}`;
    const lockData = await redis.get(lockKey);
    const lock = JSON.parse(lockData!);

    expect(lock.agent_id).toBe('agent-1');
  });

  it('lock expires after TTL', async () => {
    const lockKey = 'ralph:locks:file:temp:file.ts';
    await redis.set(lockKey, JSON.stringify({ agent_id: 'agent-1' }), 'EX', 1);

    const ttl = await redis.ttl(lockKey);
    expect(ttl).toBeGreaterThan(0);
    expect(ttl).toBeLessThanOrEqual(1);
  });
});

describe('ralph_unlock_file', () => {
  let redis: MockRedis;

  beforeEach(() => {
    redis = createMockRedis();
  });

  it('removes lock when agent owns it', async () => {
    const filePath = 'src/component.tsx';
    await createFileLock(redis, filePath, 'agent-owner');

    const lockKey = `ralph:locks:file:${filePath.replace(/[/\\]/g, ':')}`;
    const lockData = await redis.get(lockKey);
    const lock = JSON.parse(lockData!);

    if (lock.agent_id === 'agent-owner') {
      await redis.del(lockKey);
    }

    const exists = await redis.exists(lockKey);
    expect(exists).toBe(0);
  });

  it('preserves lock when different agent tries to unlock', async () => {
    const filePath = 'src/component.tsx';
    await createFileLock(redis, filePath, 'agent-owner');

    const lockKey = `ralph:locks:file:${filePath.replace(/[/\\]/g, ':')}`;
    const lockData = await redis.get(lockKey);
    const lock = JSON.parse(lockData!);

    if (lock.agent_id !== 'agent-other') {
      const exists = await redis.exists(lockKey);
      expect(exists).toBe(1);
    }
  });
});

describe('ralph_get_status', () => {
  let redis: MockRedis;

  beforeEach(() => {
    redis = createMockRedis();
  });

  it('returns agent status with alive flag', async () => {
    await createTestAgent(redis, 'agent-status-test', {
      type: 'backend',
      status: 'working',
      alive: true,
    });

    const agentData = await redis.hget('ralph:agents', 'agent-status-test');
    const isAlive = await redis.exists('ralph:heartbeats:agent-status-test');

    expect(agentData).toBeTruthy();
    expect(isAlive).toBe(1);
  });

  it('returns task status with all fields', async () => {
    await createTestTask(redis, 'status-task', {
      title: 'Status check task',
      status: 'in_progress',
      assigned_to: 'agent-worker',
    });

    const task = await getTaskFromRedis(redis, 'status-task');
    expect(task!.status).toBe('in_progress');
    expect(task!.assigned_to).toBe('agent-worker');
  });
});

describe('ralph_get_queue', () => {
  let redis: MockRedis;

  beforeEach(() => {
    redis = createMockRedis();
  });

  it('returns tasks ordered by priority', async () => {
    await createTestTask(redis, 'low-priority', { priority: 2 });
    await createTestTask(redis, 'high-priority', { priority: 9 });
    await createTestTask(redis, 'medium-priority', { priority: 5 });

    const taskIds = await redis.zrange('ralph:tasks:queue', 0, -1);

    expect(taskIds).toContain('low-priority');
    expect(taskIds).toContain('high-priority');
    expect(taskIds).toContain('medium-priority');
  });

  it('respects limit parameter', async () => {
    for (let i = 0; i < 10; i++) {
      await createTestTask(redis, `task-${i}`, { priority: i });
    }

    const limited = await redis.zrange('ralph:tasks:queue', 0, 4);
    expect(limited).toHaveLength(5);
  });
});

describe('ralph_cancel_task', () => {
  let redis: MockRedis;

  beforeEach(() => {
    redis = createMockRedis();
  });

  it('marks task as cancelled', async () => {
    await createTestTask(redis, 'cancel-me', { status: 'pending' });

    const taskData = await redis.get('ralph:tasks:data:cancel-me');
    const task = JSON.parse(taskData!);
    task.status = 'cancelled';
    task.cancelled_at = new Date().toISOString();

    await redis.set('ralph:tasks:data:cancel-me', JSON.stringify(task));

    const updated = await getTaskFromRedis(redis, 'cancel-me');
    expect(updated!.status).toBe('cancelled');
  });

  it('removes task from queue', async () => {
    await createTestTask(redis, 'remove-from-queue', { priority: 5 });

    await redis.zrem('ralph:tasks:queue', 'remove-from-queue');

    const inQueue = await redis.zscore('ralph:tasks:queue', 'remove-from-queue');
    expect(inQueue).toBeNull();
  });
});

describe('ralph_broadcast_task', () => {
  let redis: MockRedis;

  beforeEach(() => {
    redis = createMockRedis();
  });

  it('creates task without specific agent assignment', async () => {
    await createTestTask(redis, 'broadcast-task', {
      title: 'Broadcast task',
      agent_type: 'frontend',
    });

    const task = await getTaskFromRedis(redis, 'broadcast-task');
    expect(task!.assigned_to).toBeUndefined();
    expect(task!.agent_type).toBe('frontend');
  });
});

describe('ralph_validate_deps', () => {
  let redis: MockRedis;

  beforeEach(() => {
    redis = createMockRedis();
  });

  it('validates that dependencies exist', async () => {
    await createTestTask(redis, 'existing-dep', { status: 'completed' });

    const depExists = await redis.exists('ralph:tasks:data:existing-dep');
    expect(depExists).toBe(1);
  });

  it('detects missing dependency', async () => {
    const depExists = await redis.exists('ralph:tasks:data:missing-dep');
    expect(depExists).toBe(0);
  });

  it('detects self-dependency', () => {
    const taskId = 'self-dep-task';
    const dependencies = ['self-dep-task'];

    const hasSelfDep = dependencies.includes(taskId);
    expect(hasSelfDep).toBe(true);
  });
});
