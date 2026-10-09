"""Dev-only photo diagnosis for frozen candidates, never a safe-answer gate."""

import argparse
import json
import math
from pathlib import Path

from m33_objects_data import sha, write_json
from m33_verify_objects_evidence import selected, statistics


def audit(data, root, output, names=("warm", "local_only", "global_context")):
    result = json.loads(output.read_text(encoding="utf-8"))
    manifest = json.loads((data / "dataset.json").read_text(encoding="utf-8"))
    gold = [
        (r["source_id"], r["answer"])
        for r in manifest["records"]["dev"]
        if r["role"] == "VISUALLY_CURATED_NONBLIND_PHOTOGRAPH"
    ]
    if result["dataset_sha256"] != sha(data / "dataset.json"):
        raise ValueError("Probe diagnostic dataset changed")
    if set(result["candidates"]) != set(names):
        raise ValueError("All declared development anchors required")
    for name, value in result["candidates"].items():
        checkpoint = (
            root.parent / "warm.pt" if name == "warm" else root / name / "best.pt"
        )
        if value["checkpoint_sha256"] != sha(checkpoint):
            raise ValueError("Probe checkpoint changed")
        for mode in ("single_view", "five_view"):
            rows = value[mode]["records"]
            if [(r["source_id"], r["gold"]) for r in rows] != gold:
                raise ValueError("Dev photo diagnostic source/gold changed")
            for row in rows:
                if row["selected"] != selected(row["probabilities"], 0):
                    raise ValueError("Raw dev diagnostic selector changed")
            if value[mode]["raw_not_safe_policy"] != statistics(rows):
                raise ValueError("Raw dev diagnostic arithmetic changed")
            groups = {
                label: statistics([r for r in rows if r["gold"] == label])
                for label in sorted({r["gold"] for r in rows})
            }
            if value[mode]["by_available_concept"] != groups:
                raise ValueError("Raw dev concept arithmetic changed")
    return {
        "status": "AUDITED_DEV_ONLY_NO_FINAL_OR_POLICY",
        "sources": len(gold),
        "candidates": {
            name: {
                mode: value[mode]["raw_not_safe_policy"]
                for mode in ("single_view", "five_view")
            }
            for name, value in result["candidates"].items()
        },
    }


def run(data, root, output, names=("warm", "local_only", "global_context")):
    import numpy as np
    import torch
    from m33_primary_objects_pilot import ObjectPrepared, probabilities

    from ai_brain.training import primary_objects as obj

    if output.exists() or not torch.cuda.is_available():
        raise ValueError("Fresh development receipt and CUDA required")
    torch.set_num_threads(2)
    manifest = json.loads((data / "dataset.json").read_text(encoding="utf-8"))
    if sha(data / "pixels.npz") != manifest["pixels_sha256"]:
        raise ValueError("Probe diagnostic pixels changed")
    prepared = ObjectPrepared(
        np.load(data / "pixels.npz", allow_pickle=False), "dev", torch.device("cuda")
    )
    indices = [
        i
        for i, r in enumerate(manifest["records"]["dev"])
        if r["role"] == "VISUALLY_CURATED_NONBLIND_PHOTOGRAPH"
    ]
    candidates = {}
    for name in names:
        checkpoint = (
            root.parent / "warm.pt" if name == "warm" else root / name / "best.pt"
        )
        if name != "warm":
            report = json.loads((root / name / "development-report.json").read_text())
            if (
                report["checkpoint_sha256"] != sha(checkpoint)
                or report["production_admitted"]
                or report["dataset_sha256"] != sha(data / "dataset.json")
                or report["status"] != "DEVELOPMENT_ONLY_NO_CALIBRATION_OR_FINAL"
                or any(
                    (root / name / f).exists()
                    for f in (
                        "report.json",
                        "frozen-calibration.json",
                        "object-final-predictions.json",
                    )
                )
            ):
                raise ValueError("Probe development binding differs")
        model = (
            obj.ObjectsModel.from_checkpoint(
                torch.load(checkpoint, weights_only=True, map_location="cpu")
            )
            .to("cuda")
            .eval()
        )
        value = {"checkpoint_sha256": sha(checkpoint)}
        for mode, consensus in (("single_view", False), ("five_view", True)):
            probs = probabilities(model, prepared, consensus=consensus)
            rows = [
                {
                    "source_id": prepared.ids[i],
                    "gold": manifest["records"]["dev"][i]["answer"],
                    "selected": selected(probs[i], 0),
                    "probabilities": probs[i],
                }
                for i in indices
            ]
            value[mode] = {
                "records": rows,
                "raw_not_safe_policy": statistics(rows),
                "by_available_concept": {
                    label: statistics([r for r in rows if r["gold"] == label])
                    for label in sorted({r["gold"] for r in rows})
                },
            }
        value["single_view_photo_ce"] = sum(
            -math.log(
                max(
                    r["probabilities"][
                        obj.UNKNOWN
                        if r["gold"] == "UNKNOWN"
                        else obj.OBJECT_IDS[r["gold"]]
                    ],
                    1e-30,
                )
            )
            for r in value["single_view"]["records"]
        ) / len(indices)
        candidates[name] = value
        del model
    write_json(
        output,
        {
            "status": "DEV_DIAGNOSTIC_NOT_CALIBRATION_OR_FINAL",
            "candidates": candidates,
            "dataset_sha256": sha(data / "dataset.json"),
            "script_sha256": sha(Path(__file__)),
            "production_admitted": False,
            "available_photo_concepts": sorted(
                {manifest["records"]["dev"][i]["answer"] for i in indices}
            ),
            "limits": "Known curated photo development only; missing concepts are unavailable, not learned. Raw output is not the safe-answer policy. No final, calibration, regression or textbook inference here; this diagnostic never replaces a frozen selection receipt.",
        },
    )
    return audit(data, root, output, names)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("data", "root", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--capacity-probe", action="store_true")
    args = parser.parse_args()
    names = (
        ("warm", "vision64", "vision128")
        if args.capacity_probe
        else ("warm", "local_only", "global_context")
    )
    print(
        json.dumps(
            (audit if args.audit else run)(args.data, args.root, args.output, names)
        )
    )
