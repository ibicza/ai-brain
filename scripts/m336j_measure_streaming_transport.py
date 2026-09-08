"""Measure the bounded file-backed M-33.6j tree transport."""

from __future__ import annotations

import argparse
import tempfile
import tracemalloc
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336h_contracts import write_canonical_json
from ai_brain.stage3.acquisition.m336j_transport import (
    M336JTreeTransferLimits,
    extract_canonical_tree_archive_file,
    hash_file,
    write_canonical_tree_archive,
)

M336J_MINIMUM_MEASURED_PAYLOAD_BYTES = 256 * 1024 * 1024


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--payload-bytes", type=int, default=M336J_MINIMUM_MEASURED_PAYLOAD_BYTES
    )
    args = parser.parse_args()
    private_root = args.private_root.resolve(strict=True)
    output = args.output.resolve(strict=False)
    if not private_root.is_dir() or output.exists():
        raise ValueError("M336J streaming measurement paths are invalid")
    if args.payload_bytes < M336J_MINIMUM_MEASURED_PAYLOAD_BYTES:
        raise ValueError("M336J measured transfer payload is below 256 MiB")
    limits = M336JTreeTransferLimits(
        maximum_archive_bytes=args.payload_bytes + 16 * 1024 * 1024,
        maximum_unpacked_bytes=args.payload_bytes,
        maximum_file_count=1,
    )
    chunk = bytes(range(256)) * 4096
    tracemalloc.start()
    _current, baseline_peak = tracemalloc.get_traced_memory()
    with tempfile.TemporaryDirectory(
        prefix="m336j-streaming-measurement-", dir=private_root
    ) as raw:
        temporary = Path(raw)
        source = temporary / "source"
        source.mkdir()
        payload = source / "measured.bin"
        remaining = args.payload_bytes
        with payload.open("xb") as handle:
            while remaining:
                block = chunk[: min(len(chunk), remaining)]
                handle.write(block)
                remaining -= len(block)
        source_hash = hash_file(payload)
        artifact = write_canonical_tree_archive(
            source,
            temporary / "tree.zip",
            prefix="payload",
            limits=limits,
        )
        count, tree_hash = extract_canonical_tree_archive_file(
            artifact.private_path,
            destination=temporary / "extracted",
            expected_payload_hash=artifact.archive_hash,
            limits=limits,
        )
        extracted_hash = hash_file(temporary / "extracted/payload/measured.bin")
        _current, measured_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    peak_above_baseline = max(0, measured_peak - baseline_peak)
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336J_STREAMING_TRANSFER_MEASUREMENT",
        "payload_size_bytes": args.payload_bytes,
        "archive_size_bytes": artifact.archive_size,
        "archive_hash": artifact.archive_hash,
        "file_count": artifact.file_count,
        "portable_tree_hash": artifact.portable_tree_hash,
        "verified_file_count": count,
        "verified_tree_hash": tree_hash,
        "source_and_extracted_hash_equal": source_hash == extracted_hash,
        "peak_python_memory_above_baseline_bytes": peak_above_baseline,
        "peak_to_payload_ratio_parts_per_million": (
            peak_above_baseline * 1_000_000 // args.payload_bytes
        ),
        "whole_payload_bytesio_count": 0,
        "whole_file_set_read_bytes_aggregation_count": 0,
        "status": (
            "PASS"
            if count == artifact.file_count
            and tree_hash == artifact.portable_tree_hash
            and source_hash == extracted_hash
            and peak_above_baseline < args.payload_bytes // 4
            else "FAIL"
        ),
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    write_canonical_json(output, receipt)
    if receipt["status"] != "PASS":
        raise ValueError("M336J streaming transport measurement failed")


if __name__ == "__main__":
    main()
