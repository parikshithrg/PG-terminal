#!/usr/bin/env python3
"""Create or verify a consistent local PG-terminal SQLite backup."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from eod_store import EODStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create and verify a non-overwriting PG-terminal EOD-store backup."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "pg_terminal_eod.sqlite3",
    )
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    source = args.source.resolve()
    if not source.is_file():
        parser.error(f"source database does not exist: {source}")
    store = EODStore(source)
    if args.verify_only:
        report = store.integrity_report()
    else:
        if args.destination is None:
            parser.error("--destination is required unless --verify-only is used")
        report = store.create_backup(args.destination.resolve())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
