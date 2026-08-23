"""M-22.3a acquisition executable. This process has public inputs only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_brain.rules.blackbox import PublicAcquisitionTask, acquire_public_task
from ai_brain.rules.grammar import blackbox_candidate_pool


def acquire_one(request: dict) -> dict:
    return acquire_public_task(PublicAcquisitionTask.from_json(request)).to_json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("acquire", "batch", "serve"))
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--budget", type=int, default=10_000)
    args = parser.parse_args()
    if args.command == "acquire":
        print(json.dumps(acquire_one(json.loads(sys.stdin.read())), sort_keys=True))
        return
    if args.command == "serve":
        pool = blackbox_candidate_pool(args.budget)
        for line in sys.stdin:
            if not line.strip():
                continue
            task = PublicAcquisitionTask.from_json(json.loads(line))
            result = acquire_public_task(task, pool).to_json()
            print(json.dumps(result, sort_keys=True), flush=True)
        return
    if args.input is None or args.output is None:
        parser.error("batch requires --input and --output")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    requests = [
        json.loads(line)
        for line in args.input.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    pool = blackbox_candidate_pool(
        max(
            (int(row.get("candidate_budget", args.budget)) for row in requests),
            default=args.budget,
        )
    )
    with args.output.open("w", encoding="utf-8", newline="\n") as sink:
        for row in requests:
            task = PublicAcquisitionTask.from_json(row)
            result = acquire_public_task(task, pool).to_json()
            sink.write(json.dumps(result, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
