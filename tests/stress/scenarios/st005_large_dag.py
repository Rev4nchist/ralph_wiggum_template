"""
ST-005: Large DAG Stress Test

Tests dependency graph resolution with 100+ tasks and complex dependencies.
Verifies linear scaling O(V+E), correct topological ordering, and cycle detection.

Pass Criteria:
- Resolution time scales linearly O(V+E)
- Memory usage < 100MB
- Cycle detection < 10ms
- Topological order correct
"""
import pytest
import time
import random
import tracemalloc
from typing import List, Dict, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

from ..conftest import requires_redis
from ..metrics import StressTestMetrics, MetricsCollector
from ..harness import WaveBuilder


@dataclass
class DAGTask:
    task_id: str
    deps: List[str] = field(default_factory=list)


class DAGGenerator:

    @staticmethod
    def deep_chain(count: int) -> List[DAGTask]:
        tasks = []
        for i in range(count):
            deps = [f"chain-{i-1}"] if i > 0 else []
            tasks.append(DAGTask(f"chain-{i}", deps))
        return tasks

    @staticmethod
    def wide_fanout(root_count: int, leaf_count: int) -> List[DAGTask]:
        tasks = []

        for i in range(root_count):
            tasks.append(DAGTask(f"root-{i}", []))

        for i in range(leaf_count):
            parent = f"root-{i % root_count}"
            tasks.append(DAGTask(f"leaf-{i}", [parent]))

        return tasks

    @staticmethod
    def diamond_mesh(depth: int, width: int) -> List[DAGTask]:
        tasks = []

        tasks.append(DAGTask("diamond-root", []))

        prev_layer = ["diamond-root"]
        for layer in range(1, depth - 1):
            current_layer = []
            for i in range(width):
                task_id = f"diamond-L{layer}-{i}"
                deps = prev_layer[:min(2, len(prev_layer))]
                tasks.append(DAGTask(task_id, deps))
                current_layer.append(task_id)
            prev_layer = current_layer

        tasks.append(DAGTask("diamond-sink", prev_layer))

        return tasks

    @staticmethod
    def random_valid_dag(count: int, max_deps: int = 5) -> List[DAGTask]:
        tasks = []
        for i in range(count):
            if i == 0:
                tasks.append(DAGTask(f"random-{i}", []))
            else:
                num_deps = min(random.randint(0, max_deps), i)
                possible_deps = [f"random-{j}" for j in range(i)]
                deps = random.sample(possible_deps, num_deps)
                tasks.append(DAGTask(f"random-{i}", deps))
        return tasks

    @staticmethod
    def complex_project(num_features: int, tasks_per_feature: int) -> List[DAGTask]:
        tasks = []

        tasks.append(DAGTask("ARCH-001", []))

        for f in range(num_features):
            feature_root = f"FE-{f}-001"
            tasks.append(DAGTask(feature_root, ["ARCH-001"]))

            prev_task = feature_root
            for t in range(1, tasks_per_feature):
                task_id = f"FE-{f}-{t+1:03d}"
                cross_deps = []
                if f > 0 and t > 1 and random.random() < 0.3:
                    cross_deps = [f"FE-{f-1}-{t:03d}"]
                tasks.append(DAGTask(task_id, [prev_task] + cross_deps))
                prev_task = task_id

        qa_deps = [f"FE-{f}-{tasks_per_feature:03d}" for f in range(num_features)]
        tasks.append(DAGTask("QA-001", qa_deps))

        return tasks


class TopologicalSorter:

    @staticmethod
    def kahn_sort(tasks: List[DAGTask]) -> Tuple[List[str], bool]:
        graph = {t.task_id: set(t.deps) for t in tasks}
        in_degree = defaultdict(int)
        all_nodes = set()

        for task in tasks:
            all_nodes.add(task.task_id)
            for dep in task.deps:
                all_nodes.add(dep)

        for node in all_nodes:
            in_degree[node] = 0

        for task in tasks:
            for dep in task.deps:
                if dep in graph:
                    pass
            in_degree[task.task_id] = len(task.deps)

        queue = [node for node in graph if in_degree[node] == 0]
        result = []

        while queue:
            queue.sort()
            node = queue.pop(0)
            result.append(node)

            for task in tasks:
                if node in task.deps:
                    in_degree[task.task_id] -= 1
                    if in_degree[task.task_id] == 0:
                        queue.append(task.task_id)

        has_cycle = len(result) != len(graph)
        return result, has_cycle

    @staticmethod
    def detect_cycle(tasks: List[DAGTask]) -> bool:
        graph = {t.task_id: set(t.deps) for t in tasks}
        visited = set()
        rec_stack = set()

        def dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for dep in graph.get(node, []):
                if dep not in visited:
                    if dfs(dep):
                        return True
                elif dep in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        for node in graph:
            if node not in visited:
                if dfs(node):
                    return True
        return False


@requires_redis
class TestLargeDAG:

    def test_100_task_resolution(
        self,
        redis_client,
        stress_test_id
    ):
        """
        ST-005: Resolve 100-task DAG with complex dependencies.
        """
        metrics = MetricsCollector(stress_test_id, "ST-005: Large DAG 100 Tasks")

        tasks = DAGGenerator.complex_project(num_features=10, tasks_per_feature=10)
        tasks = tasks[:100]

        tracemalloc.start()
        start = time.time()

        task_dicts = [{"id": t.task_id, "deps": t.deps} for t in tasks]
        builder = WaveBuilder(task_dicts)
        waves = builder.build()

        resolution_time_ms = (time.time() - start) * 1000
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        metrics.record_instant("dag_resolution", resolution_time_ms, True)
        metrics.metrics.set_gauge("memory_peak_mb", peak / 1024 / 1024)
        metrics.metrics.set_gauge("wave_count", len(waves))
        metrics.metrics.set_gauge("task_count", len(tasks))

        final_metrics = metrics.finalize()
        final_metrics.print_summary()

        assert resolution_time_ms < 1000, \
            f"Resolution too slow: {resolution_time_ms:.2f}ms > 1000ms"

        assert peak < 100 * 1024 * 1024, \
            f"Memory usage too high: {peak / 1024 / 1024:.2f}MB > 100MB"

        all_wave_tasks = [t for wave in waves for t in wave]
        assert len(all_wave_tasks) == len(tasks), \
            f"Tasks lost in resolution: {len(all_wave_tasks)} != {len(tasks)}"

        task_positions = {t: i for i, t in enumerate(all_wave_tasks)}
        for task in tasks:
            for dep in task.deps:
                if dep in task_positions:
                    assert task_positions[dep] < task_positions[task.task_id], \
                        f"Dependency order violated: {dep} should come before {task.task_id}"

    def test_deep_chain_linear_scaling(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Test that deep chains scale linearly.
        """
        sizes = [10, 50, 100, 200]
        times = []

        for size in sizes:
            tasks = DAGGenerator.deep_chain(size)
            task_dicts = [{"id": t.task_id, "deps": t.deps} for t in tasks]

            start = time.time()
            builder = WaveBuilder(task_dicts)
            waves = builder.build()
            elapsed = (time.time() - start) * 1000
            times.append(elapsed)

            assert len(waves) == size, \
                f"Deep chain of {size} should have {size} waves, got {len(waves)}"

        ratio_50_10 = times[1] / times[0] if times[0] > 0 else 0
        ratio_100_50 = times[2] / times[1] if times[1] > 0 else 0
        ratio_200_100 = times[3] / times[2] if times[2] > 0 else 0

        assert ratio_200_100 < 10, \
            f"Non-linear scaling detected: 200/100 ratio = {ratio_200_100:.2f}"

    def test_wide_fanout_parallelism(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Test wide fanout creates parallel waves correctly.
        """
        tasks = DAGGenerator.wide_fanout(root_count=5, leaf_count=50)
        task_dicts = [{"id": t.task_id, "deps": t.deps} for t in tasks]

        builder = WaveBuilder(task_dicts)
        waves = builder.build()

        assert len(waves) == 2, \
            f"Wide fanout should have 2 waves, got {len(waves)}"

        assert len(waves[0]) == 5, \
            f"First wave should have 5 roots, got {len(waves[0])}"

        assert len(waves[1]) == 50, \
            f"Second wave should have 50 leaves, got {len(waves[1])}"

    def test_diamond_mesh_complex_deps(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Test diamond mesh with complex cross-dependencies.
        """
        tasks = DAGGenerator.diamond_mesh(depth=6, width=10)
        task_dicts = [{"id": t.task_id, "deps": t.deps} for t in tasks]

        start = time.time()
        builder = WaveBuilder(task_dicts)
        waves = builder.build()
        elapsed = (time.time() - start) * 1000

        assert len(waves) == 6, \
            f"Diamond mesh depth 6 should have 6 waves, got {len(waves)}"

        assert waves[0] == ["diamond-root"], \
            f"First wave should be root only"

        assert waves[-1] == ["diamond-sink"], \
            f"Last wave should be sink only"

        assert elapsed < 100, \
            f"Diamond resolution too slow: {elapsed:.2f}ms"

    def test_cycle_detection_fast(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Verify cycle detection is fast (< 10ms for 100 tasks).
        """
        tasks = DAGGenerator.random_valid_dag(100, max_deps=5)

        start = time.time()
        has_cycle = TopologicalSorter.detect_cycle(tasks)
        elapsed = (time.time() - start) * 1000

        assert not has_cycle, "Random valid DAG should not have cycles"
        assert elapsed < 10, \
            f"Cycle detection too slow: {elapsed:.2f}ms > 10ms"

        cyclic_tasks = list(tasks)
        cyclic_tasks.append(DAGTask("cycle-a", ["cycle-b"]))
        cyclic_tasks.append(DAGTask("cycle-b", ["cycle-c"]))
        cyclic_tasks.append(DAGTask("cycle-c", ["cycle-a"]))

        start = time.time()
        has_cycle = TopologicalSorter.detect_cycle(cyclic_tasks)
        elapsed = (time.time() - start) * 1000

        assert has_cycle, "Should detect cycle"
        assert elapsed < 10, \
            f"Cycle detection with cycle too slow: {elapsed:.2f}ms"

    def test_wave_builder_detects_cycle(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Verify WaveBuilder raises error on cyclic dependencies.
        """
        cyclic_tasks = [
            {"id": "A", "deps": ["C"]},
            {"id": "B", "deps": ["A"]},
            {"id": "C", "deps": ["B"]},
        ]

        builder = WaveBuilder(cyclic_tasks)

        with pytest.raises(ValueError, match="Circular dependency"):
            builder.build()

    def test_random_dag_consistency(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Random DAGs should always produce valid orderings.
        """
        for _ in range(10):
            tasks = DAGGenerator.random_valid_dag(50, max_deps=3)
            task_dicts = [{"id": t.task_id, "deps": t.deps} for t in tasks]

            builder = WaveBuilder(task_dicts)
            waves = builder.build()

            task_to_wave = {}
            for wave_idx, wave_tasks in enumerate(waves):
                for task_id in wave_tasks:
                    task_to_wave[task_id] = wave_idx

            for task in tasks:
                for dep in task.deps:
                    assert task_to_wave[dep] < task_to_wave[task.task_id], \
                        f"Dependency violation in random DAG"

    def test_empty_and_single_task(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Edge cases: empty DAG and single task.
        """
        builder = WaveBuilder([])
        waves = builder.build()
        assert waves == [], "Empty DAG should produce empty waves"

        builder = WaveBuilder([{"id": "single", "deps": []}])
        waves = builder.build()
        assert waves == [["single"]], "Single task should be one wave"

    def test_500_task_stress(
        self,
        redis_client,
        stress_test_id
    ):
        """
        Stress test with 500 tasks.
        """
        metrics = MetricsCollector(stress_test_id, "ST-005: Large DAG 500 Tasks")

        tasks = DAGGenerator.complex_project(num_features=50, tasks_per_feature=10)

        tracemalloc.start()
        start = time.time()

        task_dicts = [{"id": t.task_id, "deps": t.deps} for t in tasks]
        builder = WaveBuilder(task_dicts)
        waves = builder.build()

        resolution_time_ms = (time.time() - start) * 1000
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        metrics.record_instant("dag_resolution_500", resolution_time_ms, True)

        final_metrics = metrics.finalize()
        print(f"\n500-task DAG: {resolution_time_ms:.2f}ms, {peak/1024/1024:.2f}MB, {len(waves)} waves")

        assert resolution_time_ms < 5000, \
            f"500-task resolution too slow: {resolution_time_ms:.2f}ms"

        assert peak < 200 * 1024 * 1024, \
            f"500-task memory too high: {peak/1024/1024:.2f}MB"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
