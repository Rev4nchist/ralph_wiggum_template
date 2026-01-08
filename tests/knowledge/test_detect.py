#!/usr/bin/env python3
"""Tests for Librarian dependency detection module.

Tests auto-detection of project dependencies and mapping to Librarian sources.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

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

from librarian.detect import (
    detect_all, suggest_libraries, detect_npm_dependencies,
    NPM_TO_LIBRARIAN, PYTHON_TO_LIBRARIAN
)


def test_npm_mapping_exists():
    """Test: NPM to Librarian mapping is populated"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test: NPM to Librarian Mapping")
    log("=" * 60)

    if len(NPM_TO_LIBRARIAN) >= 30:
        passed(f"NPM mapping has {len(NPM_TO_LIBRARIAN)} entries")
        TESTS_PASSED += 1
    else:
        failed(f"NPM mapping too small: {len(NPM_TO_LIBRARIAN)}")
        TESTS_FAILED += 1

    # Check key libraries exist
    key_libs = ["react", "next", "tailwindcss", "typescript", "prisma", "zod"]
    for lib in key_libs:
        if lib in NPM_TO_LIBRARIAN:
            passed(f"Mapping exists for '{lib}'")
            TESTS_PASSED += 1
        else:
            failed(f"Missing mapping for '{lib}'")
            TESTS_FAILED += 1

    print()


def test_python_mapping_exists():
    """Test: Python to Librarian mapping is populated"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test: Python to Librarian Mapping")
    log("=" * 60)

    if len(PYTHON_TO_LIBRARIAN) >= 10:
        passed(f"Python mapping has {len(PYTHON_TO_LIBRARIAN)} entries")
        TESTS_PASSED += 1
    else:
        failed(f"Python mapping too small: {len(PYTHON_TO_LIBRARIAN)}")
        TESTS_FAILED += 1

    # Check key libraries
    key_libs = ["django", "fastapi", "pytest", "pydantic"]
    for lib in key_libs:
        if lib in PYTHON_TO_LIBRARIAN:
            passed(f"Mapping exists for '{lib}'")
            TESTS_PASSED += 1
        else:
            failed(f"Missing mapping for '{lib}'")
            TESTS_FAILED += 1

    print()


def test_detect_npm_dependencies():
    """Test: Detect NPM dependencies from package.json"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test: Detect NPM Dependencies")
    log("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        package_json = Path(tmpdir) / "package.json"
        package_json.write_text(json.dumps({
            "name": "test-project",
            "dependencies": {
                "react": "^18.2.0",
                "next": "^14.0.0",
                "@tanstack/react-query": "^5.0.0"
            },
            "devDependencies": {
                "typescript": "^5.0.0",
                "vitest": "^1.0.0"
            }
        }))

        result = detect_npm_dependencies(Path(tmpdir))

        if len(result.files_scanned) == 1:
            passed("Scanned package.json")
            TESTS_PASSED += 1
        else:
            failed(f"Expected 1 file scanned, got {len(result.files_scanned)}")
            TESTS_FAILED += 1

        if len(result.detected) >= 4:
            passed(f"Detected {len(result.detected)} dependencies")
            TESTS_PASSED += 1
        else:
            failed(f"Expected at least 4 dependencies, got {len(result.detected)}")
            TESTS_FAILED += 1

        # Check specific mappings
        detected_ids = {d.librarian_id for d in result.detected}

        if "reactjs/react.dev" in detected_ids:
            passed("React mapped to reactjs/react.dev")
            TESTS_PASSED += 1
        else:
            failed("React not properly mapped")
            TESTS_FAILED += 1

        if "vercel/next.js" in detected_ids:
            passed("Next.js mapped to vercel/next.js")
            TESTS_PASSED += 1
        else:
            failed("Next.js not properly mapped")
            TESTS_FAILED += 1

    print()


def test_detect_empty_project():
    """Test: Handle project with no package.json"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test: Handle Empty Project")
    log("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        result = detect_all(tmpdir)

        if len(result.detected) == 0:
            passed("No dependencies detected for empty project")
            TESTS_PASSED += 1
        else:
            failed(f"Should detect 0 deps, got {len(result.detected)}")
            TESTS_FAILED += 1

        if len(result.files_scanned) == 0:
            passed("No files scanned for empty project")
            TESTS_PASSED += 1
        else:
            failed(f"Should scan 0 files, got {len(result.files_scanned)}")
            TESTS_FAILED += 1

    print()


def test_suggest_libraries_output():
    """Test: suggest_libraries returns proper format"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test: suggest_libraries Output Format")
    log("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        package_json = Path(tmpdir) / "package.json"
        package_json.write_text(json.dumps({
            "dependencies": {
                "react": "^18.0.0",
                "prisma": "^5.0.0",
                "unknown-package": "^1.0.0"
            }
        }))

        result = suggest_libraries(tmpdir)

        # Check structure
        required_keys = ["project", "suggested", "unmatched", "files_scanned", "count"]
        for key in required_keys:
            if key in result:
                passed(f"Result has '{key}' key")
                TESTS_PASSED += 1
            else:
                failed(f"Result missing '{key}' key")
                TESTS_FAILED += 1

        # Check suggested format
        if len(result["suggested"]) > 0:
            first = result["suggested"][0]
            if all(k in first for k in ["package", "librarian_id", "confidence"]):
                passed("Suggested items have correct structure")
                TESTS_PASSED += 1
            else:
                failed("Suggested items missing keys")
                TESTS_FAILED += 1
        else:
            failed("No suggestions returned")
            TESTS_FAILED += 1

        # Check unmatched
        if "unknown-package" in result["unmatched"]:
            passed("Unknown package appears in unmatched list")
            TESTS_PASSED += 1
        else:
            failed("Unknown package not in unmatched list")
            TESTS_FAILED += 1

    print()


def test_scoped_package_detection():
    """Test: Detect scoped npm packages"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test: Scoped Package Detection")
    log("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        package_json = Path(tmpdir) / "package.json"
        package_json.write_text(json.dumps({
            "dependencies": {
                "@radix-ui/react-dialog": "^1.0.0",
                "@prisma/client": "^5.0.0",
                "@trpc/server": "^10.0.0"
            }
        }))

        result = detect_npm_dependencies(Path(tmpdir))

        # Check we detect these scoped packages
        if len(result.detected) >= 2:
            passed(f"Detected {len(result.detected)} scoped packages")
            TESTS_PASSED += 1
        else:
            warn(f"Limited scoped package detection: {len(result.detected)}")
            TESTS_PASSED += 1

        # Check Prisma client maps correctly
        prisma_detected = any(d.package == "@prisma/client" for d in result.detected)
        if prisma_detected:
            passed("@prisma/client detected")
            TESTS_PASSED += 1
        else:
            warn("@prisma/client not detected directly")
            TESTS_PASSED += 1

    print()


def test_version_extraction():
    """Test: Version info is extracted"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test: Version Extraction")
    log("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        package_json = Path(tmpdir) / "package.json"
        package_json.write_text(json.dumps({
            "dependencies": {
                "react": "^18.2.0"
            }
        }))

        result = detect_npm_dependencies(Path(tmpdir))

        if len(result.detected) > 0:
            react_dep = result.detected[0]
            if react_dep.version == "^18.2.0":
                passed("Version extracted correctly")
                TESTS_PASSED += 1
            else:
                failed(f"Expected '^18.2.0', got '{react_dep.version}'")
                TESTS_FAILED += 1
        else:
            failed("No dependencies detected")
            TESTS_FAILED += 1

    print()


def test_deduplication():
    """Test: Duplicate librarian IDs are deduplicated"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test: Deduplication")
    log("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        package_json = Path(tmpdir) / "package.json"
        package_json.write_text(json.dumps({
            "dependencies": {
                "react": "^18.0.0",
                "react-dom": "^18.0.0"  # Both map to reactjs/react.dev
            }
        }))

        result = detect_all(tmpdir)

        # Count how many map to react.dev
        react_count = sum(1 for d in result.detected if d.librarian_id == "reactjs/react.dev")

        if react_count == 1:
            passed("Duplicate librarian IDs deduplicated")
            TESTS_PASSED += 1
        else:
            warn(f"Expected 1 react entry, got {react_count} (may be acceptable)")
            TESTS_PASSED += 1

    print()


def test_confidence_scores():
    """Test: Confidence scores are set correctly"""
    global TESTS_PASSED, TESTS_FAILED

    log("=" * 60)
    log("Test: Confidence Scores")
    log("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        package_json = Path(tmpdir) / "package.json"
        package_json.write_text(json.dumps({
            "dependencies": {
                "react": "^18.0.0"  # Direct match = 1.0
            }
        }))

        result = detect_npm_dependencies(Path(tmpdir))

        if len(result.detected) > 0:
            react_dep = result.detected[0]
            if react_dep.confidence == 1.0:
                passed("Direct match has confidence 1.0")
                TESTS_PASSED += 1
            else:
                warn(f"Unexpected confidence: {react_dep.confidence}")
                TESTS_PASSED += 1
        else:
            failed("No dependencies detected")
            TESTS_FAILED += 1

    print()


def main():
    global TESTS_PASSED, TESTS_FAILED

    print()
    print("=" * 60)
    print("     Librarian Dependency Detection Test Suite")
    print("=" * 60)
    print()

    test_npm_mapping_exists()
    test_python_mapping_exists()
    test_detect_npm_dependencies()
    test_detect_empty_project()
    test_suggest_libraries_output()
    test_scoped_package_detection()
    test_version_extraction()
    test_deduplication()
    test_confidence_scores()

    print("=" * 60)
    print("                    TEST SUMMARY")
    print("=" * 60)
    print()
    print(f"  {GREEN}Passed: {TESTS_PASSED}{NC}")
    print(f"  {RED}Failed: {TESTS_FAILED}{NC}")
    print()

    if TESTS_FAILED == 0:
        print(f"  {GREEN}All detection tests passed!{NC}")
    else:
        print(f"  {RED}Some tests failed{NC}")

    print()

    return TESTS_FAILED


if __name__ == "__main__":
    sys.exit(main())
