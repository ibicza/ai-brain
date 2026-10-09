"""Controlled known-dev prompt/view robustness; no final/calibration/admission."""

import argparse
import gzip
import json
from pathlib import Path

from m33_objects_data import sha, write_json
from m33_verify_objects_evidence import selected, statistics


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def metrics(rows, threshold):
    return statistics(
        [dict(r, selected=selected(r["probabilities"], threshold)) for r in rows]
    )


def audit(data, root, records_path, report_path):
    report = load(report_path)
    with gzip.open(records_path, "rt", encoding="utf-8") as stream:
        records = json.load(stream)
    if set(records) != set(report["candidates"]):
        raise ValueError("Prompt diagnostic candidate set differs")
    if report["records_sha256"] != sha(records_path) or report["dataset_sha256"] != sha(
        data / "dataset.json"
    ):
        raise ValueError("Prompt diagnostic data/records binding differs")
    manifest = load(data / "dataset.json")
    gold = [
        (r["source_id"], r["answer"])
        for r in manifest["records"]["dev"]
        if r["role"] == "VISUALLY_CURATED_NONBLIND_PHOTOGRAPH"
    ]
    for name, groups in records.items():
        checkpoint = (
            root / "warm.pt"
            if name == "warm"
            else root / "development-v1" / name / "best.pt"
        )
        if sha(checkpoint) != report["candidates"][name]["checkpoint_sha256"]:
            raise ValueError("Prompt diagnostic checkpoint changed")
        if set(groups) != set(report["prompts"]):
            raise ValueError("Prompt group differs")
        for prompt, modes in groups.items():
            if set(modes) != {"single_view", "five_view"}:
                raise ValueError("Both declared view modes are required")
            for mode, rows in modes.items():
                if [(r["source_id"], r["gold"]) for r in rows] != gold:
                    raise ValueError("Controlled prompt diagnostic source/gold differs")
                expected = {
                    "raw_not_safe_policy": metrics(rows, 0),
                    "fixed_099_dev_only": metrics(rows, 0.99),
                }
                if report["candidates"][name]["prompts"][prompt][mode] != expected:
                    raise ValueError("Prompt diagnostic arithmetic differs")
    return {
        "status": "CONTROLLED_DEV_PROMPT_ARITHMETIC_VERIFIED",
        "unique_photos": len(gold),
        "candidates": len(records),
        "prompts": len(report["prompts"]),
        "records_sha256": sha(records_path),
        "limits": "Repeated known photos/prompt variants are not new independent sources or a fresh exam.",
    }


def run(data, root, names):
    import numpy as np
    import torch
    from m33_primary_objects_pilot import ObjectPrepared, probabilities

    from ai_brain.training import primary_objects as obj

    records_path = root / "prompt-dev-records.json.gz"
    report_path = root / "prompt-dev-diagnostic.json"
    if records_path.exists() or report_path.exists() or not torch.cuda.is_available():
        raise ValueError("Fresh output and CUDA required")
    torch.set_num_threads(2)
    manifest = load(data / "dataset.json")
    if sha(data / "pixels.npz") != manifest["pixels_sha256"]:
        raise ValueError("Frozen pixels changed")
    indices = [
        i
        for i, r in enumerate(manifest["records"]["dev"])
        if r["role"] == "VISUALLY_CURATED_NONBLIND_PHOTOGRAPH"
    ]
    archive = np.load(data / "pixels.npz", allow_pickle=False)
    subset = {
        key: archive[key][indices] for key in ("dev_pixels", "dev_ids", "dev_answers")
    }
    prepared = ObjectPrepared(subset, "dev", torch.device("cuda"))
    records, candidates = {}, {}
    for name in names:
        checkpoint = (
            root / "warm.pt"
            if name == "warm"
            else root / "development-v1" / name / "best.pt"
        )
        digest = sha(checkpoint)
        model = (
            obj.ObjectsModel.from_checkpoint(
                torch.load(checkpoint, weights_only=True, map_location="cpu")
            )
            .to("cuda")
            .eval()
        )
        records[name] = {}
        candidates[name] = {"checkpoint_sha256": digest, "prompts": {}}
        for prompt in obj.OBJECT_QUESTIONS:
            prepared.questions = torch.tensor(
                [obj.encode_question(prompt)] * len(indices), device="cuda"
            )
            records[name][prompt] = {}
            candidates[name]["prompts"][prompt] = {}
            for mode, consensus in (("single_view", False), ("five_view", True)):
                # Identical view randomness for every prompt and candidate.
                torch.manual_seed(420261009)
                probs = probabilities(model, prepared, consensus=consensus)
                rows = [
                    {
                        "source_id": prepared.ids[i],
                        "gold": manifest["records"]["dev"][original]["answer"],
                        "probabilities": probs[i],
                    }
                    for i, original in enumerate(indices)
                ]
                records[name][prompt][mode] = rows
                candidates[name]["prompts"][prompt][mode] = {
                    "raw_not_safe_policy": metrics(rows, 0),
                    "fixed_099_dev_only": metrics(rows, 0.99),
                }
        if sha(checkpoint) != digest:
            raise ValueError("Diagnostic checkpoint changed")
        del model
    with (
        records_path.open("xb") as stream,
        gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as packed,
    ):
        packed.write(
            json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
    write_json(
        report_path,
        {
            "status": "CONTROLLED_KNOWN_DEV_PROMPT_DIAGNOSTIC",
            "prompts": list(obj.OBJECT_QUESTIONS),
            "dataset_sha256": sha(data / "dataset.json"),
            "records_sha256": sha(records_path),
            "script_sha256": sha(Path(__file__)),
            "candidates": candidates,
            "production_admitted": False,
            "limits": "Same known development photos for eight supported prompts, identical view randomness. Includes already known final-question phrases, not new final images. No fitting, threshold change, final or calibration inference. Repeated variants do not increase independent sample count.",
        },
    )
    return audit(data, root, records_path, report_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("data", "root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--names", nargs="+")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            audit(
                args.data,
                args.root,
                args.root / "prompt-dev-records.json.gz",
                args.root / "prompt-dev-diagnostic.json",
            )
            if args.audit
            else run(args.data, args.root, args.names)
        )
    )
