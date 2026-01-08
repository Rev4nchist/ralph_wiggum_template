/**
 * P0 Critical Tests: Cycle Detection for Task Dependencies
 *
 * Tests the DFS-based cycle detection algorithm that prevents
 * circular dependencies between tasks (which would cause deadlocks).
 */

interface DependencyGraph {
  [taskId: string]: string[];
}

/**
 * Detect cycles in dependency graph using DFS.
 * This is the same algorithm used in the MCP server.
 */
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

describe("Cycle Detection", () => {
  describe("P0 Critical: Basic cycle detection", () => {
    test("should detect self-dependency cycle", () => {
      const graph: DependencyGraph = {};

      const result = detectCycle(graph, "task-A", ["task-A"]);

      expect(result.hasCycle).toBe(true);
      expect(result.cycle).toContain("task-A");
    });

    test("should detect two-node cycle (A → B → A)", () => {
      const graph: DependencyGraph = {
        "task-A": ["task-B"],
      };

      const result = detectCycle(graph, "task-B", ["task-A"]);

      expect(result.hasCycle).toBe(true);
      expect(result.cycle).toBeDefined();
      expect(result.cycle!.length).toBeGreaterThanOrEqual(2);
    });

    test("should detect three-node cycle (A → B → C → A)", () => {
      const graph: DependencyGraph = {
        "task-A": ["task-B"],
        "task-B": ["task-C"],
      };

      const result = detectCycle(graph, "task-C", ["task-A"]);

      expect(result.hasCycle).toBe(true);
      expect(result.cycle).toBeDefined();
    });

    test("should allow diamond pattern without cycle", () => {
      // Diamond: A → B, A → C, B → D, C → D (no cycle)
      const graph: DependencyGraph = {
        "task-A": ["task-B", "task-C"],
        "task-B": ["task-D"],
        "task-C": ["task-D"],
        "task-D": [],
      };

      const result = detectCycle(graph, "task-E", ["task-D"]);

      expect(result.hasCycle).toBe(false);
      expect(result.cycle).toBeUndefined();
    });
  });

  describe("P0 Critical: Valid dependency chains", () => {
    test("should allow linear chain (A → B → C → D)", () => {
      const graph: DependencyGraph = {
        "task-A": ["task-B"],
        "task-B": ["task-C"],
        "task-C": ["task-D"],
        "task-D": [],
      };

      const result = detectCycle(graph, "task-E", ["task-D"]);

      expect(result.hasCycle).toBe(false);
    });

    test("should allow task with no dependencies", () => {
      const graph: DependencyGraph = {
        "task-A": ["task-B"],
      };

      const result = detectCycle(graph, "task-C", []);

      expect(result.hasCycle).toBe(false);
    });

    test("should allow task depending on multiple independent tasks", () => {
      const graph: DependencyGraph = {
        "task-A": [],
        "task-B": [],
        "task-C": [],
      };

      const result = detectCycle(graph, "task-D", [
        "task-A",
        "task-B",
        "task-C",
      ]);

      expect(result.hasCycle).toBe(false);
    });

    test("should handle empty graph", () => {
      const graph: DependencyGraph = {};

      const result = detectCycle(graph, "task-A", []);

      expect(result.hasCycle).toBe(false);
    });
  });

  describe("P1 High: Complex graph scenarios", () => {
    test("should detect cycle in large graph", () => {
      // Create: 1 → 2 → 3 → 4 → 5, then 5 → 1 (cycle)
      const graph: DependencyGraph = {
        "task-1": ["task-2"],
        "task-2": ["task-3"],
        "task-3": ["task-4"],
        "task-4": ["task-5"],
      };

      const result = detectCycle(graph, "task-5", ["task-1"]);

      expect(result.hasCycle).toBe(true);
    });

    test("should detect cycle not involving new task", () => {
      // Existing cycle: A → B → A, new task: C → D
      const graph: DependencyGraph = {
        "task-A": ["task-B"],
        "task-B": ["task-A"], // existing cycle
      };

      const result = detectCycle(graph, "task-C", ["task-D"]);

      // The existing cycle should be detected
      expect(result.hasCycle).toBe(true);
    });

    test("should handle multiple separate chains", () => {
      const graph: DependencyGraph = {
        // Chain 1: A → B → C
        "task-A": ["task-B"],
        "task-B": ["task-C"],
        "task-C": [],
        // Chain 2: X → Y → Z
        "task-X": ["task-Y"],
        "task-Y": ["task-Z"],
        "task-Z": [],
      };

      const result = detectCycle(graph, "task-NEW", ["task-C", "task-Z"]);

      expect(result.hasCycle).toBe(false);
    });

    test("should detect indirect cycle through multiple nodes", () => {
      // A → B, B → C, C → D, D → E, add E → B (cycle B → C → D → E → B)
      const graph: DependencyGraph = {
        "task-A": ["task-B"],
        "task-B": ["task-C"],
        "task-C": ["task-D"],
        "task-D": ["task-E"],
      };

      const result = detectCycle(graph, "task-E", ["task-B"]);

      expect(result.hasCycle).toBe(true);
    });
  });

  describe("P2 Medium: Edge cases", () => {
    test("should handle dependency on non-existent task", () => {
      const graph: DependencyGraph = {
        "task-A": ["task-B"],
      };

      // Depending on non-existent task - no cycle
      const result = detectCycle(graph, "task-C", ["task-NONEXISTENT"]);

      expect(result.hasCycle).toBe(false);
    });

    test("should handle task with same ID as existing (replacement)", () => {
      const graph: DependencyGraph = {
        "task-A": ["task-B"],
        "task-B": [],
      };

      // "Replace" task-A with new deps
      const result = detectCycle(graph, "task-A", ["task-B"]);

      expect(result.hasCycle).toBe(false);
    });

    test("should return cycle path for debugging", () => {
      const graph: DependencyGraph = {
        "task-A": ["task-B"],
        "task-B": ["task-C"],
      };

      const result = detectCycle(graph, "task-C", ["task-A"]);

      expect(result.hasCycle).toBe(true);
      expect(result.cycle).toBeDefined();
      // Cycle should include the cyclic nodes
      expect(result.cycle!.length).toBeGreaterThan(0);
    });
  });
});
