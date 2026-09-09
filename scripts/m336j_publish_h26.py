"""Stage the source-free H26 production subset through its V2 contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage3.acquisition.m336h_contracts import (
    strict_json_file,
    write_canonical_json,
)
from ai_brain.stage3.acquisition.m336j_publication_v2 import (
    stage_m336j_h26_publication,
)

_FIELDS = {
    "repository",
    "git_executable",
    "exact_f26_sha",
    "freeze_manifest",
    "production_source",
    "output",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    request = strict_json_file(args.request)
    if not isinstance(request, dict) or set(request) != _FIELDS:
        raise ValueError("M336J H26 publisher request fields changed")
    output = Path(request["output"])
    result = stage_m336j_h26_publication(
        repository=Path(request["repository"]),
        git_executable=Path(request["git_executable"]),
        exact_f26_sha=request["exact_f26_sha"],
        freeze_manifest=Path(request["freeze_manifest"]),
        production_source=Path(request["production_source"]),
        output=output,
    )
    write_canonical_json(output / "h26_publication_report.json", result)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
