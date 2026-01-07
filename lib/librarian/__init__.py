"""Librarian Integration - External documentation search for Ralph agents

Provides access to up-to-date documentation from libraries, frameworks,
and official sources via the Librarian CLI tool.
"""

from .client import LibrarianClient
from .protocol import SearchResult, LibraryInfo

__all__ = ['LibrarianClient', 'SearchResult', 'LibraryInfo']
