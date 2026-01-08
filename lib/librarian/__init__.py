"""Librarian Integration - External documentation search for Ralph agents

Provides access to up-to-date documentation from libraries, frameworks,
and official sources via the Librarian CLI tool.
"""

from .client import LibrarianClient
from .protocol import SearchResult, LibraryInfo
from .setup_standard import load_libraries, setup_all
from .detect import detect_all, suggest_libraries, DetectedDependency, DetectionResult

__all__ = [
    'LibrarianClient', 'SearchResult', 'LibraryInfo',
    'load_libraries', 'setup_all',
    'detect_all', 'suggest_libraries', 'DetectedDependency', 'DetectionResult'
]
