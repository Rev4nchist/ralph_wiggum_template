"""Project Memory - Claude-Mem integration for multi-agent memory

Provides a unified interface for agents to store and retrieve
persistent memories that survive across sessions.
"""

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from .memory_protocol import Memory, MemoryQuery, MemoryCategory, MemoryScope


class ClaudeMemError(Exception):
    """Base exception for Claude-Mem operations."""
    pass


class ClaudeMemTimeout(ClaudeMemError):
    """Claude-Mem command timed out."""
    pass


class ClaudeMemUnavailable(ClaudeMemError):
    """Claude-Mem CLI not available."""
    pass


class ProjectMemory:
    """Unified memory interface for Ralph agents.

    Integrates with Claude-Mem for persistent storage and Redis
    for real-time coordination.
    """

    def __init__(
        self,
        project_id: str,
        agent_id: Optional[str] = None,
        redis_client: Optional[Any] = None
    ):
        self.project_id = project_id
        self.agent_id = agent_id or os.environ.get('RALPH_AGENT_ID', 'unknown')
        self.redis = redis_client

    def _claude_mem_cmd(
        self,
        action: str,
        data: Dict,
        retries: int = 2,
        silent: bool = False
    ) -> Optional[Dict]:
        """Execute Claude-Mem command with retry and error categorization.

        Args:
            action: "store" or "search"
            data: Command-specific data
            retries: Number of retry attempts (default 2)
            silent: If True, suppress exceptions and return None

        Returns:
            Command result dict or None on failure

        Raises:
            ClaudeMemTimeout: If command times out
            ClaudeMemUnavailable: If CLI not found
            ClaudeMemError: For other errors
        """
        last_error: Optional[Exception] = None

        for attempt in range(retries + 1):
            try:
                if action == "store":
                    cmd = [
                        "npx", "-y", "@anthropic-ai/claude-mem-mcp",
                        "store",
                        "--content", data.get("content", ""),
                        "--tags", ",".join(data.get("tags", []))
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    return {"success": result.returncode == 0}

                elif action == "search":
                    cmd = [
                        "npx", "-y", "@anthropic-ai/claude-mem-mcp",
                        "search",
                        "--query", data.get("query", ""),
                        "--limit", str(data.get("limit", 10))
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    if result.returncode == 0:
                        return json.loads(result.stdout) if result.stdout else {"results": []}
                    last_error = ClaudeMemError(f"Command failed with code {result.returncode}: {result.stderr}")

            except subprocess.TimeoutExpired:
                last_error = ClaudeMemTimeout(f"Timeout after 30s: {action}")
                self._log_error("timeout", action, attempt, str(last_error))
            except FileNotFoundError:
                last_error = ClaudeMemUnavailable("npx or claude-mem not found")
                self._log_error("unavailable", action, attempt, str(last_error))
                break  # Don't retry if CLI missing
            except json.JSONDecodeError as e:
                last_error = ClaudeMemError(f"Invalid JSON response: {e}")
                self._log_error("parse_error", action, attempt, str(last_error))
            except Exception as e:
                last_error = ClaudeMemError(str(e))
                self._log_error("unknown", action, attempt, str(last_error))

            if attempt < retries:
                time.sleep(0.5 * (2 ** attempt))

        if not silent and last_error:
            raise last_error
        return None

    def _log_error(self, error_type: str, action: str, attempt: int, message: str) -> None:
        """Structured error logging."""
        log_entry = {
            "level": "error",
            "component": "claude_mem",
            "error_type": error_type,
            "action": action,
            "attempt": attempt + 1,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            "project_id": self.project_id,
            "agent_id": self.agent_id
        }
        print(json.dumps(log_entry), file=sys.stderr)

    def remember(
        self,
        content: str,
        category: str = "learning",
        scope: str = "project",
        tags: Optional[List[str]] = None,
        task_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """Store a memory.

        Args:
            content: The memory content to store
            category: One of architecture, pattern, decision, blocker, learning, context, handoff, quality
            scope: project (all agents), task (task-specific), agent (personal)
            tags: Additional tags for categorization
            task_id: Associated task ID if relevant
            metadata: Additional metadata

        Returns:
            Memory ID
        """
        memory_id = f"mem-{uuid.uuid4().hex[:8]}"

        all_tags = [
            f"project:{self.project_id}",
            f"category:{category}",
            f"scope:{scope}",
            f"agent:{self.agent_id}"
        ]
        if tags:
            all_tags.extend(tags)
        if task_id:
            all_tags.append(f"task:{task_id}")

        full_content = f"""[{category.upper()}] {content}

Project: {self.project_id}
Agent: {self.agent_id}
Time: {datetime.utcnow().isoformat()}
"""

        self._claude_mem_cmd("store", {
            "content": full_content,
            "tags": all_tags
        }, silent=True)  # Silent for backward compatibility

        if self.redis:
            memory_data = {
                "id": memory_id,
                "content": content,
                "category": category,
                "scope": scope,
                "project_id": self.project_id,
                "agent_id": self.agent_id,
                "task_id": task_id,
                "tags": tags or [],
                "metadata": metadata or {},
                "created_at": datetime.utcnow().isoformat()
            }
            self.redis.hset(
                f"ralph:memory:{self.project_id}",
                memory_id,
                json.dumps(memory_data)
            )

        return memory_id

    def recall(
        self,
        query: str,
        category: Optional[str] = None,
        scope: Optional[str] = None,
        task_id: Optional[str] = None,
        limit: int = 10,
        use_cache_fallback: bool = True
    ) -> List[Memory]:
        """Recall relevant memories.

        Args:
            query: Natural language query
            category: Filter by category
            scope: Filter by scope
            task_id: Filter by task
            limit: Maximum memories to return
            use_cache_fallback: Fall back to Redis cache if Claude-Mem fails

        Returns:
            List of relevant memories
        """
        search_query = f"project:{self.project_id} {query}"
        if category:
            search_query += f" category:{category}"
        if task_id:
            search_query += f" task:{task_id}"

        try:
            result = self._claude_mem_cmd("search", {
                "query": search_query,
                "limit": limit
            }, silent=use_cache_fallback)

            memories = []
            if result and "results" in result:
                for r in result["results"]:
                    memories.append(Memory(
                        id=r.get("id", "unknown"),
                        content=r.get("content", ""),
                        category=category or "unknown",
                        scope=scope or "project",
                        project_id=self.project_id,
                        relevance_score=r.get("score", 0.0)
                    ))
                return memories

        except (ClaudeMemTimeout, ClaudeMemUnavailable):
            if use_cache_fallback and self.redis:
                return self._recall_from_redis_cache(query, category, task_id, limit)
            raise

        # If result was None (silent mode), try Redis fallback
        if use_cache_fallback and self.redis:
            return self._recall_from_redis_cache(query, category, task_id, limit)

        return []

    def _recall_from_redis_cache(
        self,
        query: str,
        category: Optional[str],
        task_id: Optional[str],
        limit: int
    ) -> List[Memory]:
        """Fallback recall from Redis cache when Claude-Mem unavailable."""
        all_memories = self.redis.hgetall(f"ralph:memory:{self.project_id}")
        matches = []
        query_lower = query.lower()

        for mem_id, mem_json in all_memories.items():
            try:
                mem_data = json.loads(mem_json)
            except json.JSONDecodeError:
                continue

            if category and mem_data.get("category") != category:
                continue
            if task_id and mem_data.get("task_id") != task_id:
                continue

            content_lower = mem_data.get("content", "").lower()
            if query_lower in content_lower or any(
                word in content_lower for word in query_lower.split()
            ):
                matches.append(Memory(
                    id=mem_data.get("id", mem_id),
                    content=mem_data.get("content", ""),
                    category=mem_data.get("category", "unknown"),
                    scope=mem_data.get("scope", "project"),
                    project_id=self.project_id,
                    relevance_score=0.5  # Lower score for cache results
                ))

        return matches[:limit]

    def note_architecture(self, decision: str, rationale: str, alternatives: Optional[List[str]] = None) -> str:
        """Record an architectural decision.

        Use this when making significant design choices that affect
        the project structure or patterns.
        """
        content = f"""DECISION: {decision}

RATIONALE: {rationale}
"""
        if alternatives:
            content += f"\nALTERNATIVES CONSIDERED:\n"
            for alt in alternatives:
                content += f"  - {alt}\n"

        return self.remember(
            content=content,
            category="architecture",
            scope="project",
            tags=["architecture", "decision"]
        )

    def note_pattern(self, pattern_name: str, description: str, example: Optional[str] = None) -> str:
        """Record a code pattern discovered or established.

        Use this when you discover or create a pattern that should
        be followed throughout the project.
        """
        content = f"""PATTERN: {pattern_name}

{description}
"""
        if example:
            content += f"\nEXAMPLE:\n```\n{example}\n```"

        return self.remember(
            content=content,
            category="pattern",
            scope="project",
            tags=["pattern", "code-style"]
        )

    def note_blocker(self, problem: str, solution: Optional[str] = None, attempts: Optional[List[str]] = None) -> str:
        """Record a blocker and its solution.

        Use this when you encounter and solve a problem that others
        might face.
        """
        content = f"""PROBLEM: {problem}
"""
        if attempts:
            content += f"\nATTEMPTS:\n"
            for attempt in attempts:
                content += f"  - {attempt}\n"

        if solution:
            content += f"\nSOLUTION: {solution}"
        else:
            content += f"\nSTATUS: Unresolved - needs human input"

        return self.remember(
            content=content,
            category="blocker",
            scope="project",
            tags=["blocker", "problem-solving"]
        )

    def handoff(self, task_id: str, summary: str, next_steps: List[str], notes: Optional[str] = None) -> str:
        """Leave handoff notes for the next agent.

        Use this when your task is complete or when you're blocked
        and another agent might continue.
        """
        content = f"""HANDOFF FOR TASK: {task_id}

SUMMARY: {summary}

NEXT STEPS:
"""
        for step in next_steps:
            content += f"  - {step}\n"

        if notes:
            content += f"\nNOTES: {notes}"

        return self.remember(
            content=content,
            category="handoff",
            scope="task",
            task_id=task_id,
            tags=["handoff", "continuity"]
        )

    def commit_task(
        self,
        task_id: str,
        summary: str,
        learnings: List[str],
        artifacts: Optional[List[str]] = None,
        quality_notes: Optional[str] = None
    ) -> str:
        """Commit task completion to memory.

        Use this when completing a task to preserve learnings
        for future reference.
        """
        content = f"""TASK COMPLETED: {task_id}

SUMMARY: {summary}

LEARNINGS:
"""
        for learning in learnings:
            content += f"  - {learning}\n"

        if artifacts:
            content += f"\nARTIFACTS:\n"
            for artifact in artifacts:
                content += f"  - {artifact}\n"

        if quality_notes:
            content += f"\nQUALITY NOTES: {quality_notes}"

        return self.remember(
            content=content,
            category="learning",
            scope="project",
            task_id=task_id,
            tags=["task-completion", "learning"]
        )

    def get_project_context(self) -> str:
        """Get full project context for starting a new task.

        Returns a formatted string with relevant project memories
        to give an agent context before starting work.
        """
        memories = self.recall(
            query="architecture decisions patterns quality standards",
            limit=20
        )

        if not memories:
            return "No project memories found. This may be a new project."

        context = "## Project Memory Context\n\n"
        for mem in memories:
            context += f"### {mem.category.upper()}\n{mem.content}\n\n"

        return context

    def get_task_context(self, task_id: str) -> str:
        """Get context for a specific task.

        Returns handoff notes and previous work on this task.
        """
        memories = self.recall(
            query="handoff notes learnings",
            task_id=task_id,
            limit=10
        )

        if not memories:
            return f"No previous context for task {task_id}."

        context = f"## Context for Task {task_id}\n\n"
        for mem in memories:
            context += f"{mem.content}\n\n"

        return context
