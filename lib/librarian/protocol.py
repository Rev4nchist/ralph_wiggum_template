"""Librarian Protocol - Data structures for documentation search"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class SearchResult:
    """A single search result from Librarian."""
    title: str
    content: str
    source: str
    library: str
    url: Optional[str] = None
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LibraryInfo:
    """Information about an indexed library."""
    name: str
    source_url: str
    docs_path: str
    ref: str = "main"
    last_indexed: Optional[datetime] = None
    doc_count: int = 0
    status: str = "unknown"


@dataclass
class IngestResult:
    """Result of ingesting documentation."""
    library: str
    success: bool
    docs_indexed: int = 0
    error: Optional[str] = None
    duration_ms: int = 0


class LibrarianError(Exception):
    """Base exception for Librarian errors."""
    pass


class LibraryNotFoundError(LibrarianError):
    """Library not found in index."""
    pass


class IngestError(LibrarianError):
    """Error during documentation ingestion."""
    pass
