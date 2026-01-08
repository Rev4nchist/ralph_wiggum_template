"""Setup Standard Libraries for Librarian

Reads standard-libraries.yaml and adds/ingests all defined libraries.

Usage:
    python -m lib.librarian.setup_standard [--add-only] [--ingest-only] [--library NAME]

Options:
    --add-only      Only add libraries (skip ingestion)
    --ingest-only   Only ingest already-added libraries
    --library NAME  Process single library by name
    --dry-run       Show what would be done without executing
    --parallel N    Ingest N libraries in parallel (default: 1)
"""

import argparse
import sys
import yaml
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Dict, Any

from .client import LibrarianClient
from .protocol import LibrarianError


SEED_FILE = Path(__file__).parent / "standard-libraries.yaml"


def load_libraries(seed_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load library definitions from YAML seed file."""
    path = seed_path or SEED_FILE
    if not path.exists():
        raise FileNotFoundError(f"Seed file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return data.get("libraries", [])


def add_library(client: LibrarianClient, lib: Dict[str, Any], dry_run: bool = False) -> bool:
    """Add a single library to Librarian."""
    name = lib["name"]
    repo = lib["repo"]
    docs_path = lib.get("docs_path", "docs")
    branch = lib.get("branch", "main")

    source_url = f"https://github.com/{repo}"

    print(f"  Adding {name}: {repo} ({docs_path}@{branch})")

    if dry_run:
        print(f"    [DRY RUN] Would add {source_url}")
        return True

    try:
        client.add_library(
            source_url=source_url,
            name=name,
            docs_path=docs_path,
            ref=branch
        )
        print(f"    Added successfully")
        return True
    except LibrarianError as e:
        print(f"    FAILED: {e}")
        return False


def ingest_library(client: LibrarianClient, name: str, dry_run: bool = False) -> bool:
    """Ingest documentation for a library."""
    print(f"  Ingesting {name}...")

    if dry_run:
        print(f"    [DRY RUN] Would ingest {name}")
        return True

    try:
        result = client.ingest(name)
        if result.success:
            print(f"    Indexed {result.docs_indexed} documents in {result.duration_ms}ms")
            return True
        else:
            print(f"    FAILED: {result.error}")
            return False
    except LibrarianError as e:
        print(f"    FAILED: {e}")
        return False


def setup_all(
    add_only: bool = False,
    ingest_only: bool = False,
    library_filter: Optional[str] = None,
    dry_run: bool = False,
    parallel: int = 1,
    seed_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Setup all standard libraries.

    Returns:
        Dict with 'added', 'ingested', 'failed' counts
    """
    client = LibrarianClient()

    if not client.is_available():
        print("ERROR: Librarian CLI not found. Install with:")
        print("  npm install -g @iannuttall/librarian")
        return {"added": 0, "ingested": 0, "failed": 0}

    libraries = load_libraries(seed_path)

    if library_filter:
        libraries = [lib for lib in libraries if lib["name"] == library_filter]
        if not libraries:
            print(f"ERROR: Library '{library_filter}' not found in seed file")
            return {"added": 0, "ingested": 0, "failed": 0}

    stats = {"added": 0, "ingested": 0, "failed": 0}

    if not ingest_only:
        print(f"\n=== Adding {len(libraries)} libraries ===\n")
        for lib in libraries:
            if add_library(client, lib, dry_run):
                stats["added"] += 1
            else:
                stats["failed"] += 1

    if not add_only:
        print(f"\n=== Ingesting {len(libraries)} libraries ===\n")

        if parallel > 1:
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                futures = {
                    executor.submit(ingest_library, client, lib["name"], dry_run): lib["name"]
                    for lib in libraries
                }
                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        if future.result():
                            stats["ingested"] += 1
                        else:
                            stats["failed"] += 1
                    except Exception as e:
                        print(f"    {name} FAILED: {e}")
                        stats["failed"] += 1
        else:
            for lib in libraries:
                if ingest_library(client, lib["name"], dry_run):
                    stats["ingested"] += 1
                else:
                    stats["failed"] += 1

    print(f"\n=== Summary ===")
    print(f"  Added: {stats['added']}")
    print(f"  Ingested: {stats['ingested']}")
    print(f"  Failed: {stats['failed']}")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Setup standard libraries for Librarian",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("--add-only", action="store_true", help="Only add libraries")
    parser.add_argument("--ingest-only", action="store_true", help="Only ingest libraries")
    parser.add_argument("--library", type=str, help="Process single library by name")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--parallel", type=int, default=1, help="Parallel ingestion workers")
    parser.add_argument("--seed-file", type=str, help="Custom seed file path")

    args = parser.parse_args()

    seed_path = Path(args.seed_file) if args.seed_file else None

    stats = setup_all(
        add_only=args.add_only,
        ingest_only=args.ingest_only,
        library_filter=args.library,
        dry_run=args.dry_run,
        parallel=args.parallel,
        seed_path=seed_path
    )

    sys.exit(0 if stats["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
