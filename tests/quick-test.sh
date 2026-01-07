#!/bin/bash
cd "$(dirname "$0")/.."

echo "Ralph Wiggum Integration Test"
echo "============================="
echo ""

REDIS="docker-compose exec -T redis redis-cli"

echo "Phase 1: Infrastructure"
$REDIS ping | head -1
echo "MCP: $(test -f mcp-server/dist/index.js && echo OK || echo MISSING)"

echo ""
echo "Phase 2: Agent Registration"
$REDIS HSET ralph:agents a1 test > /dev/null
echo "Agent: $($REDIS HGET ralph:agents a1 | head -1)"
$REDIS SETEX ralph:hb:a1 30 now > /dev/null
echo "Heartbeat: $($REDIS EXISTS ralph:hb:a1 | head -1)"

echo ""
echo "Phase 3: Task Queue"
$REDIS SET ralph:tasks:t1 data > /dev/null
$REDIS ZADD ralph:q 1000 t1 > /dev/null
echo "Queue: $($REDIS ZRANGE ralph:q 0 -1 | head -1)"
$REDIS SETNX ralph:claim:t1 agent > /dev/null
echo "Claimed: $($REDIS GET ralph:claim:t1 | head -1)"

echo ""
echo "Phase 4: File Locking"
$REDIS SET ralph:lock:f1 a1 NX EX 60 > /dev/null
echo "Lock: $($REDIS GET ralph:lock:f1 | head -1)"
$REDIS DEL ralph:lock:f1 > /dev/null
echo "Released: $($REDIS EXISTS ralph:lock:f1 | head -1)"

echo ""
echo "Phase 5: Memory"
$REDIS HSET ralph:mem:p1 m1 testdata > /dev/null
echo "Memory: $($REDIS HGET ralph:mem:p1 m1 | head -1)"

echo ""
echo "Phase 6: Pub/Sub"
echo "Publish: $($REDIS PUBLISH ralph:events test)"

echo ""
$REDIS FLUSHDB > /dev/null
echo "============================="
echo "ALL TESTS COMPLETE"
echo "============================="
