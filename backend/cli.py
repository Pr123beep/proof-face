from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from .pipeline import Pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Face scan → social reverse-image match → EVM evidence record")
    parser.add_argument("image", type=Path, help="Path to a JPEG, PNG, or WEBP portrait")
    parser.add_argument("--json", action="store_true", help="Print only the final JSON result")
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error(f"Image does not exist: {args.image}")

    case_id = uuid.uuid4().hex[:12]

    def update(stage: str, progress: int, message: str) -> None:
        if not args.json:
            print(f"[{progress:>3}%] {stage.upper():<8} {message}", flush=True)

    try:
        result = Pipeline().run(case_id, args.image.read_bytes(), args.image.name, update)
        print(json.dumps(result, indent=2))
        return 0
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
