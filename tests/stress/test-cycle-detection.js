#!/usr/bin/env node
/**
 * Test script for cycle detection in Ralph task dependencies
 * Pure algorithm test - no external dependencies required
 */

const GREEN = "\x1b[32m";
const RED = "\x1b[31m";
const YELLOW = "\x1b[33m";
const BLUE = "\x1b[34m";
const NC = "\x1b[0m";

const pass = (msg) => console.log(`${GREEN}[PASS]${NC} ${msg}`);
const fail = (msg) => console.log(`${RED}[FAIL]${NC} ${msg}`);
const log = (msg) => console.log(`${BLUE}[TEST]${NC} ${msg}`);
const warn = (msg) => console.log(`${YELLOW}[WARN]${NC} ${msg}`);

// Cycle detection algorithm (same as MCP server)
function detectCycle(graph, newTaskId, newDeps) {
  const tempGraph = { ...graph, [newTaskId]: newDeps };

  const visited = new Set();
  const recStack = new Set();
  const path = [];

  function dfs(node) {
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

let testsPassed = 0;
let testsFailed = 0;

async function runTests() {
  console.log("");
  console.log("╔═══════════════════════════════════════════════════════════════╗");
  console.log("║        Cycle Detection Unit Tests                             ║");
  console.log("╚═══════════════════════════════════════════════════════════════╝");
  console.log("");

  // Test 1: Direct self-cycle (A → A)
  log("Test 1: Direct self-cycle (A → A)");
  {
    const graph = {};
    const result = detectCycle(graph, "A", ["A"]);
    if (result.hasCycle && result.cycle.includes("A")) {
      pass("Self-cycle detected");
      testsPassed++;
    } else {
      fail("Self-cycle NOT detected");
      testsFailed++;
    }
  }

  // Test 2: Simple two-node cycle (A → B → A)
  log("Test 2: Two-node cycle (A → B → A)");
  {
    const graph = { A: ["B"] };
    const result = detectCycle(graph, "B", ["A"]);
    if (result.hasCycle) {
      pass(`Cycle detected: ${result.cycle.join(" → ")}`);
      testsPassed++;
    } else {
      fail("Two-node cycle NOT detected");
      testsFailed++;
    }
  }

  // Test 3: Three-node cycle (A → B → C → A)
  log("Test 3: Three-node cycle (A → B → C → A)");
  {
    const graph = { A: ["B"], B: ["C"] };
    const result = detectCycle(graph, "C", ["A"]);
    if (result.hasCycle) {
      pass(`Cycle detected: ${result.cycle.join(" → ")}`);
      testsPassed++;
    } else {
      fail("Three-node cycle NOT detected");
      testsFailed++;
    }
  }

  // Test 4: Diamond dependency (NO cycle)
  log("Test 4: Diamond dependency (A→B,C B→D C→D) - should be VALID");
  {
    const graph = { A: [], B: ["A"], C: ["A"] };
    const result = detectCycle(graph, "D", ["B", "C"]);
    if (!result.hasCycle) {
      pass("Diamond correctly identified as acyclic");
      testsPassed++;
    } else {
      fail(`False positive: ${result.cycle.join(" → ")}`);
      testsFailed++;
    }
  }

  // Test 5: Adding dep that creates indirect cycle
  log("Test 5: Indirect cycle via new dependency");
  {
    // Existing: A → B → C
    // Adding: C → A creates cycle
    const graph = { A: ["B"], B: ["C"], C: [] };
    const result = detectCycle(graph, "C", ["A"]);
    if (result.hasCycle) {
      pass(`Indirect cycle detected: ${result.cycle.join(" → ")}`);
      testsPassed++;
    } else {
      fail("Indirect cycle NOT detected");
      testsFailed++;
    }
  }

  // Test 6: Large acyclic graph
  log("Test 6: Large acyclic graph (10 nodes)");
  {
    const graph = {
      T1: [],
      T2: ["T1"],
      T3: ["T1"],
      T4: ["T2", "T3"],
      T5: ["T4"],
      T6: ["T4"],
      T7: ["T5", "T6"],
      T8: ["T7"],
      T9: ["T8"],
    };
    const result = detectCycle(graph, "T10", ["T9"]);
    if (!result.hasCycle) {
      pass("Large acyclic graph correctly identified");
      testsPassed++;
    } else {
      fail(`False positive in large graph: ${result.cycle.join(" → ")}`);
      testsFailed++;
    }
  }

  // Test 7: Cycle in existing graph (not just new node)
  log("Test 7: Detect existing cycle in graph");
  {
    // Graph already has cycle: X → Y → Z → X
    const graph = { X: ["Y"], Y: ["Z"], Z: ["X"] };
    const result = detectCycle(graph, "NEW", []);
    if (result.hasCycle) {
      pass(`Existing cycle detected: ${result.cycle.join(" → ")}`);
      testsPassed++;
    } else {
      fail("Existing cycle NOT detected");
      testsFailed++;
    }
  }

  // Test 8: Empty dependencies (should always be valid)
  log("Test 8: Empty dependencies (always valid)");
  {
    const graph = { A: ["B"], B: ["C"] };
    const result = detectCycle(graph, "D", []);
    if (!result.hasCycle) {
      pass("Empty dependencies correctly validated");
      testsPassed++;
    } else {
      fail("False positive on empty dependencies");
      testsFailed++;
    }
  }

  // Summary
  console.log("");
  console.log("═══════════════════════════════════════════════════════════════");
  console.log("                    TEST SUMMARY");
  console.log("═══════════════════════════════════════════════════════════════");
  console.log("");
  console.log(`  ${GREEN}Passed: ${testsPassed}${NC}`);
  console.log(`  ${RED}Failed: ${testsFailed}${NC}`);
  console.log("");

  if (testsFailed === 0) {
    console.log(`  ${GREEN}✅ All cycle detection tests passed!${NC}`);
  } else {
    console.log(`  ${RED}❌ Some tests failed${NC}`);
  }
  console.log("");

  process.exit(testsFailed);
}

runTests().catch(console.error);
