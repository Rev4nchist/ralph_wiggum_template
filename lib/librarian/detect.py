"""Auto-detect project dependencies for Librarian indexing.

Scans project files to identify dependencies and suggests libraries to index.
Supports: package.json (Node), requirements.txt (Python), Cargo.toml (Rust), etc.
"""

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

# Mapping of npm packages to Librarian sources
NPM_TO_LIBRARIAN = {
    "react": "reactjs/react.dev",
    "react-dom": "reactjs/react.dev",
    "next": "vercel/next.js",
    "vue": "vuejs/docs",
    "@vue/cli": "vuejs/docs",
    "tailwindcss": "tailwindlabs/tailwindcss.com",
    "typescript": "microsoft/TypeScript",
    "prisma": "prisma/docs",
    "@prisma/client": "prisma/docs",
    "zod": "colinhacks/zod",
    "@tanstack/react-query": "TanStack/query",
    "react-query": "TanStack/query",
    "vitest": "vitest-dev/vitest",
    "jest": "jestjs/jest",
    "zustand": "pmndrs/zustand",
    "jotai": "pmndrs/jotai",
    "playwright": "microsoft/playwright",
    "@playwright/test": "microsoft/playwright",
    "express": "expressjs/expressjs.com",
    "fastify": "fastify/fastify",
    "hono": "honojs/hono",
    "drizzle-orm": "drizzle-team/drizzle-orm",
    "date-fns": "date-fns/date-fns",
    "dayjs": "iamkun/dayjs",
    "axios": "axios/axios",
    "trpc": "trpc/trpc",
    "@trpc/server": "trpc/trpc",
    "@trpc/client": "trpc/trpc",
    "astro": "withastro/docs",
    "svelte": "sveltejs/svelte",
    "@sveltejs/kit": "sveltejs/kit",
    "remix": "remix-run/remix",
    "@remix-run/react": "remix-run/remix",
    "vite": "vitejs/vite",
    "esbuild": "evanw/esbuild",
    "turbo": "vercel/turbo",
    "nx": "nrwl/nx",
    "supabase": "supabase/supabase",
    "@supabase/supabase-js": "supabase/supabase",
    "firebase": "firebase/firebase-js-sdk",
    "mongoose": "Automattic/mongoose",
    "sequelize": "sequelize/sequelize",
    "typeorm": "typeorm/typeorm",
    "kysely": "kysely-org/kysely",
    "socket.io": "socketio/socket.io",
    "lodash": "lodash/lodash",
    "ramda": "ramda/ramda",
    "radix-ui": "radix-ui/primitives",
    "@radix-ui/react-dialog": "radix-ui/primitives",
    "shadcn-ui": "shadcn-ui/ui",
    "chakra-ui": "chakra-ui/chakra-ui",
    "@chakra-ui/react": "chakra-ui/chakra-ui",
    "material-ui": "mui/material-ui",
    "@mui/material": "mui/material-ui",
    "antd": "ant-design/ant-design",
}

# Python packages
PYTHON_TO_LIBRARIAN = {
    "django": "django/django",
    "flask": "pallets/flask",
    "fastapi": "tiangolo/fastapi",
    "pydantic": "pydantic/pydantic",
    "sqlalchemy": "sqlalchemy/sqlalchemy",
    "pytest": "pytest-dev/pytest",
    "requests": "psf/requests",
    "httpx": "encode/httpx",
    "celery": "celery/celery",
    "pandas": "pandas-dev/pandas",
    "numpy": "numpy/numpy",
    "pytorch": "pytorch/pytorch",
    "tensorflow": "tensorflow/tensorflow",
    "langchain": "langchain-ai/langchain",
    "openai": "openai/openai-python",
    "anthropic": "anthropics/anthropic-sdk-python",
}


@dataclass
class DetectedDependency:
    """A detected dependency with its Librarian source."""
    package: str
    version: Optional[str]
    source: str
    librarian_id: str
    confidence: float  # 0-1


@dataclass
class DetectionResult:
    """Result of dependency detection."""
    project_path: str
    detected: List[DetectedDependency]
    unmatched: List[str]
    files_scanned: List[str]


def detect_npm_dependencies(project_path: Path) -> DetectionResult:
    """Detect dependencies from package.json."""
    package_json = project_path / "package.json"
    detected = []
    unmatched = []
    files_scanned = []

    if not package_json.exists():
        return DetectionResult(str(project_path), [], [], [])

    files_scanned.append(str(package_json))

    try:
        with open(package_json) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return DetectionResult(str(project_path), [], [], files_scanned)

    deps = {}
    deps.update(data.get("dependencies", {}))
    deps.update(data.get("devDependencies", {}))

    for pkg, version in deps.items():
        # Normalize package name
        pkg_normalized = pkg.lower()

        # Direct match
        if pkg in NPM_TO_LIBRARIAN:
            detected.append(DetectedDependency(
                package=pkg,
                version=version,
                source="npm",
                librarian_id=NPM_TO_LIBRARIAN[pkg],
                confidence=1.0
            ))
            continue

        # Check for scoped package prefix match
        matched = False
        for npm_pkg, lib_id in NPM_TO_LIBRARIAN.items():
            if pkg.startswith(f"@{npm_pkg.split('/')[0]}/") or pkg.startswith(npm_pkg):
                detected.append(DetectedDependency(
                    package=pkg,
                    version=version,
                    source="npm",
                    librarian_id=lib_id,
                    confidence=0.8
                ))
                matched = True
                break

        if not matched:
            unmatched.append(pkg)

    return DetectionResult(str(project_path), detected, unmatched, files_scanned)


def detect_python_dependencies(project_path: Path) -> DetectionResult:
    """Detect dependencies from requirements.txt or pyproject.toml."""
    detected = []
    unmatched = []
    files_scanned = []

    # Check requirements.txt
    requirements_txt = project_path / "requirements.txt"
    if requirements_txt.exists():
        files_scanned.append(str(requirements_txt))
        try:
            with open(requirements_txt) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    # Parse package name (handle ==, >=, etc.)
                    match = re.match(r"([a-zA-Z0-9_-]+)", line)
                    if match:
                        pkg = match.group(1).lower()
                        version_match = re.search(r"[=<>!]+(.+)$", line)
                        version = version_match.group(1) if version_match else None

                        if pkg in PYTHON_TO_LIBRARIAN:
                            detected.append(DetectedDependency(
                                package=pkg,
                                version=version,
                                source="pypi",
                                librarian_id=PYTHON_TO_LIBRARIAN[pkg],
                                confidence=1.0
                            ))
                        else:
                            unmatched.append(pkg)
        except IOError:
            pass

    # Check pyproject.toml
    pyproject = project_path / "pyproject.toml"
    if pyproject.exists():
        files_scanned.append(str(pyproject))
        try:
            import tomllib
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)

            deps = data.get("project", {}).get("dependencies", [])
            if isinstance(deps, list):
                for dep in deps:
                    match = re.match(r"([a-zA-Z0-9_-]+)", dep)
                    if match:
                        pkg = match.group(1).lower()
                        if pkg in PYTHON_TO_LIBRARIAN:
                            detected.append(DetectedDependency(
                                package=pkg,
                                version=None,
                                source="pypi",
                                librarian_id=PYTHON_TO_LIBRARIAN[pkg],
                                confidence=1.0
                            ))
                        else:
                            unmatched.append(pkg)
        except (ImportError, IOError, Exception):
            pass

    return DetectionResult(str(project_path), detected, unmatched, files_scanned)


def detect_all(project_path: str) -> DetectionResult:
    """Detect all dependencies from a project."""
    path = Path(project_path)

    all_detected: List[DetectedDependency] = []
    all_unmatched: Set[str] = set()
    all_files: List[str] = []

    # Detect npm
    npm_result = detect_npm_dependencies(path)
    all_detected.extend(npm_result.detected)
    all_unmatched.update(npm_result.unmatched)
    all_files.extend(npm_result.files_scanned)

    # Detect Python
    py_result = detect_python_dependencies(path)
    all_detected.extend(py_result.detected)
    all_unmatched.update(py_result.unmatched)
    all_files.extend(py_result.files_scanned)

    # Deduplicate by librarian_id
    seen_ids = set()
    unique_detected = []
    for dep in all_detected:
        if dep.librarian_id not in seen_ids:
            seen_ids.add(dep.librarian_id)
            unique_detected.append(dep)

    return DetectionResult(
        project_path=str(path),
        detected=unique_detected,
        unmatched=sorted(all_unmatched - {d.package for d in unique_detected}),
        files_scanned=all_files
    )


def suggest_libraries(project_path: str) -> Dict:
    """Get library suggestions for a project.

    Returns a dict suitable for JSON output with:
    - suggested: list of libraries to index
    - unmatched: packages without library mappings
    - files_scanned: which files were analyzed
    """
    result = detect_all(project_path)

    return {
        "project": result.project_path,
        "suggested": [
            {
                "package": d.package,
                "librarian_id": d.librarian_id,
                "source": d.source,
                "version": d.version,
                "confidence": d.confidence
            }
            for d in result.detected
        ],
        "unmatched": result.unmatched,
        "files_scanned": result.files_scanned,
        "count": len(result.detected)
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Detect project dependencies for Librarian")
    parser.add_argument("path", nargs="?", default=".", help="Project path to scan")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    suggestions = suggest_libraries(args.path)

    if args.json:
        print(json.dumps(suggestions, indent=2))
    else:
        print(f"\nProject: {suggestions['project']}")
        print(f"Files scanned: {', '.join(suggestions['files_scanned']) or 'None'}")
        print(f"\nSuggested libraries ({suggestions['count']}):")

        for lib in suggestions["suggested"]:
            conf = "★" if lib["confidence"] == 1.0 else "☆"
            ver = f" ({lib['version']})" if lib["version"] else ""
            print(f"  {conf} {lib['package']}{ver} → {lib['librarian_id']}")

        if suggestions["unmatched"]:
            print(f"\nUnmatched packages ({len(suggestions['unmatched'])}):")
            for pkg in suggestions["unmatched"][:10]:
                print(f"  - {pkg}")
            if len(suggestions["unmatched"]) > 10:
                print(f"  ... and {len(suggestions['unmatched']) - 10} more")
