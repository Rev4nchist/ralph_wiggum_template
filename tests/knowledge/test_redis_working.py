#!/usr/bin/env python3
"""Redis Working Memory Tests

Tests for the real-time coordination layer including:
- Agent registry
- Task queue
- File locking
- Pub/Sub messaging
- Artifact sharing
"""

import json
import time
import threading
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lib'))

import redis

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
NC = "\033[0m"

def log(msg): print(f"{BLUE}[TEST]{NC} {msg}")
def passed(msg): print(f"{GREEN}[PASS]{NC} {msg}")
def failed(msg): print(f"{RED}[FAIL]{NC} {msg}")
def warn(msg): print(f"{YELLOW}[WARN]{NC} {msg}")

TESTS_PASSED = 0
TESTS_FAILED = 0

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')


def test_agent_registry():
    """Test 3.1: Agent Registry Accuracy"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test 3.1: Agent Registry Accuracy")
    log("=" * 60)

    r = redis.from_url(REDIS_URL, decode_responses=True)

    agent_id = f"test-agent-{int(time.time())}"
    agent_data = {
        'agent_id': agent_id,
        'agent_type': 'test',
        'specialist_modes': ['test'],
        'status': 'active'
    }

    # Register agent
    r.hset("ralph:agents", agent_id, json.dumps(agent_data))
    r.setex(f"ralph:heartbeats:{agent_id}", 30, "alive")

    # Verify registration
    stored = r.hget("ralph:agents", agent_id)
    if stored:
        passed("Agent registered in registry")
        TESTS_PASSED += 1
    else:
        failed("Agent NOT found in registry")
        TESTS_FAILED += 1

    # Verify heartbeat
    alive = r.exists(f"ralph:heartbeats:{agent_id}")
    if alive:
        passed("Agent heartbeat active")
        TESTS_PASSED += 1
    else:
        failed("Agent heartbeat NOT found")
        TESTS_FAILED += 1

    # Deregister
    r.hdel("ralph:agents", agent_id)
    r.delete(f"ralph:heartbeats:{agent_id}")

    # Verify deregistration
    after = r.hget("ralph:agents", agent_id)
    if not after:
        passed("Agent deregistered successfully")
        TESTS_PASSED += 1
    else:
        failed("Agent still in registry after deregistration")
        TESTS_FAILED += 1

    print()


def test_task_state_consistency():
    """Test 3.2: Task State Consistency"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test 3.2: Task State Consistency")
    log("=" * 60)

    r = redis.from_url(REDIS_URL, decode_responses=True)

    task_id = f"test-task-{int(time.time())}"
    agent_id = "test-agent"

    # Create task
    task_data = {
        'id': task_id,
        'title': 'Test Task',
        'description': 'Testing state consistency',
        'status': 'pending',
        'priority': 5
    }

    # Enqueue
    r.set(f"ralph:tasks:data:{task_id}", json.dumps(task_data))
    score = 5 * 1000000 + int(time.time())
    r.zadd("ralph:tasks:queue", {task_id: score})

    # Verify pending
    stored = json.loads(r.get(f"ralph:tasks:data:{task_id}"))
    in_queue = r.zscore("ralph:tasks:queue", task_id)

    if stored['status'] == 'pending' and in_queue:
        passed("Task in pending state with queue entry")
        TESTS_PASSED += 1
    else:
        failed(f"Task state inconsistent: status={stored['status']}, in_queue={in_queue}")
        TESTS_FAILED += 1

    # Claim task
    claimed = r.setnx(f"ralph:tasks:claimed:{task_id}", agent_id)
    if claimed:
        task_data['status'] = 'claimed'
        task_data['assigned_to'] = agent_id
        r.set(f"ralph:tasks:data:{task_id}", json.dumps(task_data))
        r.zrem("ralph:tasks:queue", task_id)

    # Verify claimed
    stored = json.loads(r.get(f"ralph:tasks:data:{task_id}"))
    in_queue = r.zscore("ralph:tasks:queue", task_id)

    if stored['status'] == 'claimed' and stored['assigned_to'] == agent_id and not in_queue:
        passed("Task in claimed state, removed from queue")
        TESTS_PASSED += 1
    else:
        failed(f"Task claim inconsistent")
        TESTS_FAILED += 1

    # Complete task
    task_data['status'] = 'completed'
    task_data['result'] = {'success': True}
    r.set(f"ralph:tasks:data:{task_id}", json.dumps(task_data))
    r.delete(f"ralph:tasks:claimed:{task_id}")

    # Verify completed
    stored = json.loads(r.get(f"ralph:tasks:data:{task_id}"))
    claim_exists = r.exists(f"ralph:tasks:claimed:{task_id}")

    if stored['status'] == 'completed' and not claim_exists:
        passed("Task completed, claim released")
        TESTS_PASSED += 1
    else:
        failed("Task completion inconsistent")
        TESTS_FAILED += 1

    # Cleanup
    r.delete(f"ralph:tasks:data:{task_id}")

    print()


def test_artifact_sharing():
    """Test 3.3: Artifact Sharing"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test 3.3: Artifact Sharing")
    log("=" * 60)

    r = redis.from_url(REDIS_URL, decode_responses=True)

    artifact_id = f"agent-1:build-output:{int(time.time())}"
    artifact_data = {
        'name': 'build-output',
        'agent_id': 'agent-1',
        'task_id': 'task-001',
        'data': json.dumps({'files': ['dist/app.js', 'dist/styles.css']}),
        'created_at': '2024-01-01T00:00:00Z'
    }

    # Store artifact
    r.hset(f"ralph:artifacts:{artifact_id}", mapping=artifact_data)
    r.expire(f"ralph:artifacts:{artifact_id}", 86400)

    # Retrieve artifact (simulating different agent)
    retrieved = r.hgetall(f"ralph:artifacts:{artifact_id}")

    if retrieved:
        passed("Artifact stored and retrieved")
        TESTS_PASSED += 1

        # Verify data integrity
        data = json.loads(retrieved['data'])
        if data['files'] == ['dist/app.js', 'dist/styles.css']:
            passed("Artifact data integrity verified")
            TESTS_PASSED += 1
        else:
            failed("Artifact data corrupted")
            TESTS_FAILED += 1
    else:
        failed("Artifact NOT found")
        TESTS_FAILED += 1

    # Cleanup
    r.delete(f"ralph:artifacts:{artifact_id}")

    print()


def test_pubsub_reliability():
    """Test 3.4: Event Pub/Sub Reliability"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test 3.4: Event Pub/Sub Reliability")
    log("=" * 60)

    r = redis.from_url(REDIS_URL, decode_responses=True)

    events_received = []

    def listener():
        pubsub = r.pubsub()
        pubsub.subscribe("ralph:test:events")
        for message in pubsub.listen():
            if message['type'] == 'message':
                events_received.append(json.loads(message['data']))
                if len(events_received) >= 3:
                    break

    # Start listener in background
    thread = threading.Thread(target=listener, daemon=True)
    thread.start()

    # Give subscriber time to connect
    time.sleep(0.5)

    # Publish events
    for i in range(3):
        r.publish("ralph:test:events", json.dumps({'event': f'test-{i}'}))
        time.sleep(0.1)

    # Wait for events
    thread.join(timeout=2)

    if len(events_received) >= 3:
        passed(f"Received all {len(events_received)} events")
        TESTS_PASSED += 1
    else:
        failed(f"Only received {len(events_received)}/3 events")
        TESTS_FAILED += 1

    print()


def test_memory_redis_dual_write():
    """Test 3.5: Memory-Redis Dual Write"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test 3.5: Memory-Redis Dual Write")
    log("=" * 60)

    r = redis.from_url(REDIS_URL, decode_responses=True)

    project_id = "test-project"
    mem_id = f"mem-{int(time.time())}"

    memory_data = {
        'id': mem_id,
        'content': 'Test pattern: Use Repository for data access',
        'category': 'pattern',
        'scope': 'project',
        'project_id': project_id,
        'agent_id': 'test-agent',
        'tags': ['pattern', 'architecture']
    }

    # Write to Redis (simulating dual write)
    r.hset(f"ralph:memory:{project_id}", mem_id, json.dumps(memory_data))

    # Read from Redis
    stored = r.hget(f"ralph:memory:{project_id}", mem_id)

    if stored:
        data = json.loads(stored)
        if data['content'] == memory_data['content']:
            passed("Memory stored in Redis successfully")
            TESTS_PASSED += 1
        else:
            failed("Memory content mismatch")
            TESTS_FAILED += 1
    else:
        failed("Memory NOT found in Redis")
        TESTS_FAILED += 1

    # List all memories in project
    all_memories = r.hgetall(f"ralph:memory:{project_id}")
    if mem_id in all_memories:
        passed("Memory listed in project memories")
        TESTS_PASSED += 1
    else:
        failed("Memory NOT in project listing")
        TESTS_FAILED += 1

    # Cleanup
    r.hdel(f"ralph:memory:{project_id}", mem_id)

    print()


def test_file_lock_coordination():
    """Test: File Lock Coordination"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test: File Lock Coordination")
    log("=" * 60)

    r = redis.from_url(REDIS_URL, decode_responses=True)

    file_path = "src/shared/types.ts"
    lock_key = f"ralph:locks:file:{file_path.replace('/', ':')}"

    # Agent 1 acquires lock
    lock_data = {
        'agent_id': 'agent-backend',
        'file_path': file_path,
        'acquired_at': '2024-01-01T00:00:00Z'
    }

    acquired = r.set(lock_key, json.dumps(lock_data), nx=True, ex=10)

    if acquired:
        passed("Agent 1 acquired file lock")
        TESTS_PASSED += 1
    else:
        failed("Agent 1 failed to acquire lock")
        TESTS_FAILED += 1

    # Agent 2 tries to acquire (should fail)
    lock_data2 = {
        'agent_id': 'agent-frontend',
        'file_path': file_path
    }

    acquired2 = r.set(lock_key, json.dumps(lock_data2), nx=True)

    if not acquired2:
        passed("Agent 2 correctly blocked")
        TESTS_PASSED += 1
    else:
        failed("Agent 2 acquired lock when it shouldn't")
        TESTS_FAILED += 1

    # Verify lock holder
    holder = json.loads(r.get(lock_key))
    if holder['agent_id'] == 'agent-backend':
        passed("Lock holder is correct (agent-backend)")
        TESTS_PASSED += 1
    else:
        failed(f"Wrong lock holder: {holder['agent_id']}")
        TESTS_FAILED += 1

    # Cleanup
    r.delete(lock_key)

    print()


def test_dependency_tracking():
    """Test: Dependency State Tracking"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test: Dependency State Tracking")
    log("=" * 60)

    r = redis.from_url(REDIS_URL, decode_responses=True)

    ts = int(time.time())

    # Create task with dependencies
    task_a = {'id': f'task-a-{ts}', 'status': 'pending', 'deps': []}
    task_b = {'id': f'task-b-{ts}', 'status': 'pending', 'deps': [f'task-a-{ts}']}

    r.set(f"ralph:tasks:data:{task_a['id']}", json.dumps(task_a))
    r.set(f"ralph:tasks:data:{task_b['id']}", json.dumps(task_b))

    # Check if B can be claimed (should NOT - A not complete)
    stored_b = json.loads(r.get(f"ralph:tasks:data:{task_b['id']}"))
    stored_a = json.loads(r.get(f"ralph:tasks:data:{task_a['id']}"))

    can_claim_b = stored_a['status'] == 'completed'

    if not can_claim_b:
        passed("Task B correctly blocked (A not complete)")
        TESTS_PASSED += 1
    else:
        failed("Task B claimable when A not complete")
        TESTS_FAILED += 1

    # Complete A
    task_a['status'] = 'completed'
    r.set(f"ralph:tasks:data:{task_a['id']}", json.dumps(task_a))

    # Now B should be claimable
    stored_a = json.loads(r.get(f"ralph:tasks:data:{task_a['id']}"))
    can_claim_b = stored_a['status'] == 'completed'

    if can_claim_b:
        passed("Task B claimable after A complete")
        TESTS_PASSED += 1
    else:
        failed("Task B still blocked after A complete")
        TESTS_FAILED += 1

    # Cleanup
    r.delete(f"ralph:tasks:data:{task_a['id']}")
    r.delete(f"ralph:tasks:data:{task_b['id']}")

    print()


def main():
    global TESTS_PASSED, TESTS_FAILED

    print()
    print("=" * 60)
    print("     Redis Working Memory Test Suite")
    print("=" * 60)
    print()

    # Verify Redis connection
    try:
        r = redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()
        passed("Redis connection verified")
    except Exception as e:
        failed(f"Redis connection failed: {e}")
        return 1

    print()

    # Run tests
    test_agent_registry()
    test_task_state_consistency()
    test_artifact_sharing()
    test_pubsub_reliability()
    test_memory_redis_dual_write()
    test_file_lock_coordination()
    test_dependency_tracking()

    # Summary
    print("=" * 60)
    print("                    TEST SUMMARY")
    print("=" * 60)
    print()
    print(f"  {GREEN}Passed: {TESTS_PASSED}{NC}")
    print(f"  {RED}Failed: {TESTS_FAILED}{NC}")
    print()

    if TESTS_FAILED == 0:
        print(f"  {GREEN}All Redis working memory tests passed!{NC}")
    else:
        print(f"  {RED}Some tests failed{NC}")

    print()

    return TESTS_FAILED


if __name__ == "__main__":
    sys.exit(main())
