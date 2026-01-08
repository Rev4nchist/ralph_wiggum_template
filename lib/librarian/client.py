"""Librarian Client - Interface to @iannuttall/librarian CLI

Provides programmatic access to:
- Documentation search (keyword + semantic)
- Library management (add, ingest, list)
- MCP server integration
"""

import json
import os
import subprocess
import shutil
from typing import List, Optional, Dict, Any
from datetime import datetime

from .protocol import (
    SearchResult, LibraryInfo, IngestResult,
    LibrarianError, LibraryNotFoundError, IngestError
)


class LibrarianClient:
    """Client for interacting with Librarian documentation search.

    CLI Commands Wrapped:
        - librarian search "query" --library "lib" --mode word|vector|hybrid --json
        - librarian add github.com/owner/repo --docs-path "path" --branch "branch"
        - librarian list (shows all sources)
        - librarian embed --source ID --force (embeds a source)

    Usage:
        client = LibrarianClient()

        # Search documentation
        results = client.search("react hooks", library="react", mode="hybrid")

        # List indexed libraries
        libraries = client.list_libraries()

        # Add and embed a new library
        client.add_library("github.com/vercel/next.js", docs_path="docs")
        client.embed("nextjs", force=True)
    """

    def __init__(
        self,
        config_dir: Optional[str] = None,
        timeout: int = 60
    ):
        """Initialize Librarian client.

        Args:
            config_dir: Custom config directory (default: ~/.config/librarian)
            timeout: Command timeout in seconds
        """
        self.config_dir = config_dir or os.path.expanduser("~/.config/librarian")
        self.timeout = timeout
        self._librarian_path = self._find_librarian()

    def _find_librarian(self) -> Optional[str]:
        """Find the librarian executable."""
        librarian = shutil.which("librarian")
        if librarian:
            return librarian

        npm_global = os.path.expanduser("~/.npm-global/bin/librarian")
        if os.path.exists(npm_global):
            return npm_global

        npx_path = shutil.which("npx")
        if npx_path:
            return None

        return None

    def _run_command(
        self,
        args: List[str],
        timeout: Optional[int] = None
    ) -> subprocess.CompletedProcess:
        """Run a librarian command."""
        timeout = timeout or self.timeout

        if self._librarian_path:
            cmd = [self._librarian_path] + args
        else:
            cmd = ["npx", "-y", "@iannuttall/librarian"] + args

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "LIBRARIAN_CONFIG": self.config_dir}
            )
            return result
        except subprocess.TimeoutExpired:
            raise LibrarianError(f"Command timed out after {timeout}s: {' '.join(args)}")
        except Exception as e:
            raise LibrarianError(f"Failed to run librarian: {e}")

    def is_available(self) -> bool:
        """Check if Librarian is installed and available."""
        try:
            result = self._run_command(["--version"], timeout=10)
            return result.returncode == 0
        except:
            return False

    def search(
        self,
        query: str,
        library: Optional[str] = None,
        limit: int = 10,
        mode: str = "hybrid"
    ) -> List[SearchResult]:
        """Search documentation.

        Args:
            query: Search query (natural language)
            library: Filter to specific library
            limit: Maximum results to return
            mode: Search mode - "word", "vector", or "hybrid" (default)

        Returns:
            List of SearchResult objects
        """
        args = ["search", query]

        if library:
            args.extend(["--library", library])

        args.extend(["--mode", mode])
        args.append("--json")

        result = self._run_command(args)

        if result.returncode != 0:
            if "not found" in result.stderr.lower():
                raise LibraryNotFoundError(f"Library not found: {library}")
            raise LibrarianError(f"Search failed: {result.stderr}")

        try:
            data = json.loads(result.stdout) if result.stdout.strip() else {"results": []}
        except json.JSONDecodeError:
            return self._parse_text_results(result.stdout)

        results = []
        for item in data.get("results", []):
            results.append(SearchResult(
                title=item.get("title", "Untitled"),
                content=item.get("content", ""),
                source=item.get("source", ""),
                library=item.get("library", library or "unknown"),
                url=item.get("url"),
                score=item.get("score", 0.0),
                metadata=item.get("metadata", {})
            ))

        return results

    def _parse_text_results(self, output: str) -> List[SearchResult]:
        """Parse text output when JSON not available."""
        results = []
        current_result = {}

        for line in output.split("\n"):
            line = line.strip()
            if not line:
                if current_result:
                    results.append(SearchResult(
                        title=current_result.get("title", "Result"),
                        content=current_result.get("content", ""),
                        source=current_result.get("source", ""),
                        library=current_result.get("library", "unknown"),
                        score=current_result.get("score", 0.0)
                    ))
                    current_result = {}
                continue

            if line.startswith("Title:"):
                current_result["title"] = line[6:].strip()
            elif line.startswith("Source:"):
                current_result["source"] = line[7:].strip()
            elif line.startswith("Score:"):
                try:
                    current_result["score"] = float(line[6:].strip())
                except ValueError:
                    pass
            elif line.startswith("Library:"):
                current_result["library"] = line[8:].strip()
            else:
                current_result["content"] = current_result.get("content", "") + line + "\n"

        if current_result:
            results.append(SearchResult(
                title=current_result.get("title", "Result"),
                content=current_result.get("content", ""),
                source=current_result.get("source", ""),
                library=current_result.get("library", "unknown"),
                score=current_result.get("score", 0.0)
            ))

        return results

    def list_libraries(self) -> List[LibraryInfo]:
        """List all indexed libraries (sources)."""
        result = self._run_command(["list"])

        if result.returncode != 0:
            raise LibrarianError(f"Failed to list libraries: {result.stderr}")

        try:
            data = json.loads(result.stdout) if result.stdout.strip() else {"libraries": []}
        except json.JSONDecodeError:
            return []

        libraries = []
        for item in data.get("libraries", []):
            libraries.append(LibraryInfo(
                name=item.get("name", "unknown"),
                source_url=item.get("source_url", ""),
                docs_path=item.get("docs_path", ""),
                ref=item.get("ref", "main"),
                last_indexed=datetime.fromisoformat(item["last_indexed"]) if item.get("last_indexed") else None,
                doc_count=item.get("doc_count", 0),
                status=item.get("status", "unknown")
            ))

        return libraries

    def add_library(
        self,
        source_url: str,
        name: Optional[str] = None,
        docs_path: Optional[str] = None,
        branch: str = "main"
    ) -> bool:
        """Add a library source for indexing.

        Args:
            source_url: GitHub repo URL (e.g., github.com/owner/repo)
            name: Library name (auto-detected if not provided)
            docs_path: Path to docs within repo (optional)
            branch: Git branch (default: main)

        Returns:
            True if successful
        """
        args = ["add", source_url]

        if docs_path:
            args.extend(["--docs-path", docs_path])

        args.extend(["--branch", branch])

        if name:
            args.extend(["--name", name])

        result = self._run_command(args, timeout=120)

        if result.returncode != 0:
            raise LibrarianError(f"Failed to add library: {result.stderr}")

        return True

    def embed(self, source_id: str, force: bool = False) -> IngestResult:
        """Embed (index) documentation for a source.

        This generates embeddings for the documentation.

        Args:
            source_id: Source ID to embed
            force: Force re-embedding even if already done

        Returns:
            IngestResult with status
        """
        start_time = datetime.now()

        args = ["embed", "--source", source_id]
        if force:
            args.append("--force")

        result = self._run_command(args, timeout=300)

        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        if result.returncode != 0:
            return IngestResult(
                library=source_id,
                success=False,
                error=result.stderr,
                duration_ms=duration_ms
            )

        try:
            data = json.loads(result.stdout) if result.stdout.strip() else {}
            docs_indexed = data.get("docs_indexed", 0)
        except json.JSONDecodeError:
            docs_indexed = 0
            if result.stdout:
                import re
                match = re.search(r"(\d+)\s+documents", result.stdout)
                if match:
                    docs_indexed = int(match.group(1))

        return IngestResult(
            library=source_id,
            success=True,
            docs_indexed=docs_indexed,
            duration_ms=duration_ms
        )

    def ingest(self, library: str) -> IngestResult:
        """Alias for embed() for backwards compatibility."""
        return self.embed(library, force=False)

    def get_document(self, library: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific document by ID.

        Args:
            library: Library name
            doc_id: Document ID

        Returns:
            Document content or None
        """
        result = self._run_command(["get", library, doc_id, "--json"])

        if result.returncode != 0:
            return None

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"content": result.stdout}

    def search_for_api(self, api_name: str, library: str) -> List[SearchResult]:
        """Search specifically for API documentation.

        Convenience method for finding function/class/method documentation.
        """
        return self.search(
            f"{api_name} API reference usage example",
            library=library,
            limit=5,
            mode="hybrid"
        )

    def search_for_error(self, error_message: str, library: Optional[str] = None) -> List[SearchResult]:
        """Search for error message solutions.

        Convenience method for troubleshooting.
        """
        query = f"error {error_message} solution fix troubleshooting"
        return self.search(query, library=library, limit=10)

    def search_for_pattern(self, pattern_name: str, library: Optional[str] = None) -> List[SearchResult]:
        """Search for implementation patterns.

        Convenience method for finding best practices.
        """
        query = f"{pattern_name} pattern best practice example implementation"
        return self.search(query, library=library, limit=10)


class MockLibrarianClient(LibrarianClient):
    """Mock client for testing without Librarian installed."""

    def __init__(self, mock_data: Optional[Dict[str, Any]] = None):
        self.mock_data = mock_data or {}
        self._libraries = {}
        self._search_results = {}

    def is_available(self) -> bool:
        return True

    def add_mock_library(self, name: str, docs: List[Dict[str, str]]) -> None:
        """Add mock library data for testing."""
        self._libraries[name] = LibraryInfo(
            name=name,
            source_url=f"https://github.com/mock/{name}",
            docs_path="docs",
            doc_count=len(docs),
            status="indexed"
        )
        self._search_results[name] = docs

    def search(
        self,
        query: str,
        library: Optional[str] = None,
        limit: int = 10,
        mode: str = "hybrid"
    ) -> List[SearchResult]:
        results = []

        search_in = [library] if library else list(self._search_results.keys())

        for lib in search_in:
            if lib not in self._search_results:
                continue

            for doc in self._search_results[lib]:
                query_lower = query.lower()
                content_lower = doc.get("content", "").lower()
                title_lower = doc.get("title", "").lower()

                if any(term in content_lower or term in title_lower
                       for term in query_lower.split()):
                    results.append(SearchResult(
                        title=doc.get("title", "Mock Result"),
                        content=doc.get("content", ""),
                        source=doc.get("source", "mock"),
                        library=lib,
                        score=0.8
                    ))

        return results[:limit]

    def list_libraries(self) -> List[LibraryInfo]:
        return list(self._libraries.values())

    def add_library(self, source_url: str, name: Optional[str] = None,
                   docs_path: Optional[str] = None, branch: str = "main") -> bool:
        lib_name = name or source_url.split("/")[-1].replace(".git", "")
        self._libraries[lib_name] = LibraryInfo(
            name=lib_name,
            source_url=source_url,
            docs_path=docs_path or "docs",
            ref=branch,
            status="added"
        )
        return True

    def embed(self, source_id: str, force: bool = False) -> IngestResult:
        if source_id not in self._libraries:
            return IngestResult(library=source_id, success=False, error="Source not found")

        self._libraries[source_id].status = "indexed"
        return IngestResult(
            library=source_id,
            success=True,
            docs_indexed=self._libraries[source_id].doc_count
        )

    def ingest(self, library: str) -> IngestResult:
        """Alias for embed() for backwards compatibility."""
        return self.embed(library, force=False)
