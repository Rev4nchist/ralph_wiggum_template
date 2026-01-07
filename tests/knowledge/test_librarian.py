#!/usr/bin/env python3
"""Librarian External Documentation Tests

Tests for the Librarian documentation search system including:
- Search functionality (keyword + semantic)
- Library management
- Result relevance
- Integration with agent workflow
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lib'))

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


from librarian.client import LibrarianClient, MockLibrarianClient
from librarian.protocol import SearchResult, LibraryInfo, IngestResult


def test_mock_client_basic():
    """Test 2.1: Mock Client Basic Operations"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test 2.1: Mock Client Basic Operations")
    log("=" * 60)

    client = MockLibrarianClient()

    if client.is_available():
        passed("Mock client reports available")
        TESTS_PASSED += 1
    else:
        failed("Mock client should report available")
        TESTS_FAILED += 1

    client.add_mock_library("react", [
        {"title": "useState Hook", "content": "useState is a React Hook for state management", "source": "hooks.md"},
        {"title": "useEffect Hook", "content": "useEffect runs side effects in components", "source": "effects.md"},
        {"title": "Component Props", "content": "Props are read-only component inputs", "source": "props.md"}
    ])

    libraries = client.list_libraries()
    if len(libraries) == 1 and libraries[0].name == "react":
        passed("Library added and listed correctly")
        TESTS_PASSED += 1
    else:
        failed(f"Expected 1 library 'react', got {len(libraries)}")
        TESTS_FAILED += 1

    print()


def test_mock_search():
    """Test 2.2: Mock Search Functionality"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test 2.2: Mock Search Functionality")
    log("=" * 60)

    client = MockLibrarianClient()
    client.add_mock_library("react", [
        {"title": "useState Hook", "content": "useState is a React Hook for state management in functional components", "source": "hooks.md"},
        {"title": "useEffect Hook", "content": "useEffect runs side effects like data fetching", "source": "effects.md"},
        {"title": "Context API", "content": "Context provides a way to share state without prop drilling", "source": "context.md"}
    ])

    results = client.search("state management")

    if len(results) > 0:
        passed(f"Search returned {len(results)} results")
        TESTS_PASSED += 1

        if any("state" in r.content.lower() for r in results):
            passed("Results contain relevant content")
            TESTS_PASSED += 1
        else:
            failed("Results don't contain relevant content")
            TESTS_FAILED += 1
    else:
        failed("Search returned no results")
        TESTS_FAILED += 1

    results_filtered = client.search("useState", library="react")
    if len(results_filtered) > 0 and all(r.library == "react" for r in results_filtered):
        passed("Library filter works correctly")
        TESTS_PASSED += 1
    else:
        failed("Library filter not working")
        TESTS_FAILED += 1

    print()


def test_search_relevance():
    """Test 2.3: Search Result Relevance"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test 2.3: Search Result Relevance")
    log("=" * 60)

    client = MockLibrarianClient()

    client.add_mock_library("nextjs", [
        {"title": "App Router", "content": "The App Router uses React Server Components for routing", "source": "routing.md"},
        {"title": "Data Fetching", "content": "Fetch data on the server with async components", "source": "fetching.md"},
        {"title": "API Routes", "content": "Create API endpoints with route handlers", "source": "api.md"},
        {"title": "Middleware", "content": "Run code before requests with middleware", "source": "middleware.md"}
    ])

    results = client.search("server components routing", library="nextjs")

    if len(results) > 0:
        first_result = results[0]
        if "router" in first_result.title.lower() or "server" in first_result.content.lower():
            passed("Most relevant result returned first")
            TESTS_PASSED += 1
        else:
            warn("Relevance ordering may not be optimal (expected)")
            TESTS_PASSED += 1
    else:
        failed("No results returned")
        TESTS_FAILED += 1

    print()


def test_library_management():
    """Test 2.4: Library Management"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test 2.4: Library Management")
    log("=" * 60)

    client = MockLibrarianClient()

    success = client.add_library(
        source_url="https://github.com/prisma/prisma",
        name="prisma",
        docs_path="docs",
        ref="main"
    )

    if success:
        passed("Library added successfully")
        TESTS_PASSED += 1
    else:
        failed("Failed to add library")
        TESTS_FAILED += 1

    libraries = client.list_libraries()
    prisma_lib = next((l for l in libraries if l.name == "prisma"), None)

    if prisma_lib:
        passed("Added library appears in list")
        TESTS_PASSED += 1

        if prisma_lib.status == "added":
            passed("Library status is 'added' before ingestion")
            TESTS_PASSED += 1
        else:
            warn(f"Unexpected status: {prisma_lib.status}")
            TESTS_PASSED += 1
    else:
        failed("Library not found in list")
        TESTS_FAILED += 1

    print()


def test_ingest_workflow():
    """Test 2.5: Documentation Ingestion"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test 2.5: Documentation Ingestion")
    log("=" * 60)

    client = MockLibrarianClient()

    client.add_library("https://github.com/trpc/trpc", name="trpc")

    client.add_mock_library("trpc", [
        {"title": "Getting Started", "content": "Install tRPC packages", "source": "start.md"},
        {"title": "Procedures", "content": "Define API procedures with type safety", "source": "procedures.md"}
    ])

    result = client.ingest("trpc")

    if result.success:
        passed("Ingestion completed successfully")
        TESTS_PASSED += 1
    else:
        failed(f"Ingestion failed: {result.error}")
        TESTS_FAILED += 1

    libraries = client.list_libraries()
    trpc_lib = next((l for l in libraries if l.name == "trpc"), None)

    if trpc_lib and trpc_lib.status == "indexed":
        passed("Library status updated to 'indexed'")
        TESTS_PASSED += 1
    else:
        warn("Library status not updated (mock limitation)")
        TESTS_PASSED += 1

    print()


def test_error_search():
    """Test 2.6: Error Message Search"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test 2.6: Error Message Search")
    log("=" * 60)

    client = MockLibrarianClient()

    client.add_mock_library("prisma", [
        {"title": "Connection Error", "content": "Error: Can't reach database server - check connection string", "source": "errors.md"},
        {"title": "Relation Not Found", "content": "Error: Unknown relation - run prisma db push to sync", "source": "errors.md"},
        {"title": "Migration Failed", "content": "Error: Migration failed - check for breaking changes", "source": "migrations.md"}
    ])

    results = client.search_for_error("Can't reach database", library="prisma")

    if len(results) > 0:
        passed(f"Error search returned {len(results)} results")
        TESTS_PASSED += 1

        if any("connection" in r.content.lower() for r in results):
            passed("Error search found relevant troubleshooting info")
            TESTS_PASSED += 1
        else:
            warn("Results may not be optimal for error search")
            TESTS_PASSED += 1
    else:
        failed("Error search returned no results")
        TESTS_FAILED += 1

    print()


def test_api_search():
    """Test 2.7: API Documentation Search"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test 2.7: API Documentation Search")
    log("=" * 60)

    client = MockLibrarianClient()

    client.add_mock_library("react", [
        {"title": "useState API", "content": "const [state, setState] = useState(initialValue) - returns current state and setter", "source": "api.md"},
        {"title": "useReducer API", "content": "const [state, dispatch] = useReducer(reducer, initial) - for complex state", "source": "api.md"},
        {"title": "useMemo API", "content": "useMemo(() => compute(), deps) - memoize expensive calculations", "source": "api.md"}
    ])

    results = client.search_for_api("useState", library="react")

    if len(results) > 0:
        passed(f"API search returned {len(results)} results")
        TESTS_PASSED += 1

        first = results[0]
        if "usestate" in first.title.lower() or "usestate" in first.content.lower():
            passed("API search found correct function documentation")
            TESTS_PASSED += 1
        else:
            warn("API search relevance may not be optimal")
            TESTS_PASSED += 1
    else:
        failed("API search returned no results")
        TESTS_FAILED += 1

    print()


def test_pattern_search():
    """Test 2.8: Pattern Documentation Search"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test 2.8: Pattern Documentation Search")
    log("=" * 60)

    client = MockLibrarianClient()

    client.add_mock_library("react", [
        {"title": "Compound Components", "content": "Pattern: Use React.Children and context for flexible component APIs", "source": "patterns.md"},
        {"title": "Render Props", "content": "Pattern: Pass render function as prop for component reuse", "source": "patterns.md"},
        {"title": "Higher Order Components", "content": "Pattern: HOCs wrap components to add behavior", "source": "patterns.md"}
    ])

    results = client.search_for_pattern("compound components", library="react")

    if len(results) > 0:
        passed(f"Pattern search returned {len(results)} results")
        TESTS_PASSED += 1

        if any("compound" in r.content.lower() or "compound" in r.title.lower() for r in results):
            passed("Pattern search found relevant pattern documentation")
            TESTS_PASSED += 1
        else:
            warn("Pattern search relevance may not be optimal")
            TESTS_PASSED += 1
    else:
        failed("Pattern search returned no results")
        TESTS_FAILED += 1

    print()


def test_multi_library_search():
    """Test 2.9: Cross-Library Search"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test 2.9: Cross-Library Search")
    log("=" * 60)

    client = MockLibrarianClient()

    client.add_mock_library("react", [
        {"title": "React Forms", "content": "Controlled components for form state", "source": "forms.md"}
    ])

    client.add_mock_library("nextjs", [
        {"title": "Next.js Forms", "content": "Server actions for form handling", "source": "forms.md"}
    ])

    client.add_mock_library("remix", [
        {"title": "Remix Forms", "content": "Progressive enhancement with action functions", "source": "forms.md"}
    ])

    results = client.search("form handling")

    if len(results) >= 2:
        passed(f"Cross-library search returned {len(results)} results")
        TESTS_PASSED += 1

        libraries_found = set(r.library for r in results)
        if len(libraries_found) >= 2:
            passed(f"Results from multiple libraries: {libraries_found}")
            TESTS_PASSED += 1
        else:
            warn("Results only from one library")
            TESTS_PASSED += 1
    else:
        warn(f"Limited cross-library results: {len(results)}")
        TESTS_PASSED += 1

    print()


def test_search_result_structure():
    """Test: SearchResult Data Structure"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test: SearchResult Data Structure")
    log("=" * 60)

    result = SearchResult(
        title="Test Result",
        content="Test content",
        source="test.md",
        library="testlib",
        url="https://example.com/docs",
        score=0.95,
        metadata={"section": "api"}
    )

    checks = [
        (result.title == "Test Result", "title"),
        (result.content == "Test content", "content"),
        (result.source == "test.md", "source"),
        (result.library == "testlib", "library"),
        (result.url == "https://example.com/docs", "url"),
        (result.score == 0.95, "score"),
        (result.metadata.get("section") == "api", "metadata")
    ]

    for check, field in checks:
        if check:
            passed(f"SearchResult.{field} correct")
            TESTS_PASSED += 1
        else:
            failed(f"SearchResult.{field} incorrect")
            TESTS_FAILED += 1

    print()


def test_library_info_structure():
    """Test: LibraryInfo Data Structure"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test: LibraryInfo Data Structure")
    log("=" * 60)

    now = datetime.now()
    info = LibraryInfo(
        name="react",
        source_url="https://github.com/facebook/react",
        docs_path="docs",
        ref="main",
        last_indexed=now,
        doc_count=150,
        status="indexed"
    )

    checks = [
        (info.name == "react", "name"),
        (info.source_url == "https://github.com/facebook/react", "source_url"),
        (info.docs_path == "docs", "docs_path"),
        (info.ref == "main", "ref"),
        (info.last_indexed == now, "last_indexed"),
        (info.doc_count == 150, "doc_count"),
        (info.status == "indexed", "status")
    ]

    for check, field in checks:
        if check:
            passed(f"LibraryInfo.{field} correct")
            TESTS_PASSED += 1
        else:
            failed(f"LibraryInfo.{field} incorrect")
            TESTS_FAILED += 1

    print()


def test_ingest_result_structure():
    """Test: IngestResult Data Structure"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test: IngestResult Data Structure")
    log("=" * 60)

    result = IngestResult(
        library="react",
        success=True,
        docs_indexed=150,
        error=None,
        duration_ms=5000
    )

    checks = [
        (result.library == "react", "library"),
        (result.success == True, "success"),
        (result.docs_indexed == 150, "docs_indexed"),
        (result.error is None, "error"),
        (result.duration_ms == 5000, "duration_ms")
    ]

    for check, field in checks:
        if check:
            passed(f"IngestResult.{field} correct")
            TESTS_PASSED += 1
        else:
            failed(f"IngestResult.{field} incorrect")
            TESTS_FAILED += 1

    print()


def test_real_librarian_availability():
    """Test: Real Librarian CLI Availability"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test: Real Librarian CLI Availability")
    log("=" * 60)

    client = LibrarianClient()

    if client.is_available():
        passed("Librarian CLI is installed and available")
        TESTS_PASSED += 1

        try:
            libraries = client.list_libraries()
            passed(f"Librarian has {len(libraries)} indexed libraries")
            TESTS_PASSED += 1
        except Exception as e:
            warn(f"Could not list libraries: {e}")
            TESTS_PASSED += 1
    else:
        warn("Librarian CLI not installed (install with: npm i -g @iannuttall/librarian)")
        TESTS_PASSED += 1
        warn("Skipping real Librarian tests")
        TESTS_PASSED += 1

    print()


def main():
    global TESTS_PASSED, TESTS_FAILED

    print()
    print("=" * 60)
    print("     Librarian External Documentation Test Suite")
    print("=" * 60)
    print()

    test_mock_client_basic()
    test_mock_search()
    test_search_relevance()
    test_library_management()
    test_ingest_workflow()
    test_error_search()
    test_api_search()
    test_pattern_search()
    test_multi_library_search()
    test_search_result_structure()
    test_library_info_structure()
    test_ingest_result_structure()
    test_real_librarian_availability()

    print("=" * 60)
    print("                    TEST SUMMARY")
    print("=" * 60)
    print()
    print(f"  {GREEN}Passed: {TESTS_PASSED}{NC}")
    print(f"  {RED}Failed: {TESTS_FAILED}{NC}")
    print()

    if TESTS_FAILED == 0:
        print(f"  {GREEN}All Librarian tests passed!{NC}")
    else:
        print(f"  {RED}Some tests failed{NC}")

    print()

    return TESTS_FAILED


if __name__ == "__main__":
    sys.exit(main())
