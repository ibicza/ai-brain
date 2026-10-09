"""Five sequential, protected own-weight development iterations with auditable lineage.

Do not confuse five rounds of adaptive development with five independent exams.
The unchanged acceptance needs a separately sourced fresh final if dev becomes viable.
"""

import json
import os
import subprocess
from pathlib import Path

from m33_objects_context_probe_report import run as dev_photos
from m33_objects_data import sha, write_json
from m33_primary_objects_pilot import POLICY_SHA, PREVIOUS_SHA
from m33_verify_objects_evidence import selected, statistics

PYTHON = "/home/ibicza/ai-brain/.venv/bin/python"
WARM = "54d1767db8befa55fc8d6633cff788453eafff6e951ab04c65fa64338a4e2590"
DATA = "c71dce559b11274b16aaf21bd9f0588e22fb5d7d99e4f7656437ef3bc9c9cf21"
TRIALS = (
    {
        "name": "iteration1_pair_js",
        "consistency_weight": 1.0,
        "supervised_contrastive_weight": 0,
        "vicreg_weight": 0,
        "object_readout_adapter": False,
        "object_prompt_balancing": False,
        "reason": "Train aligned labels on two views and penalize inconsistent answer distributions.",
    },
    {
        "name": "iteration2_supcon",
        "consistency_weight": 1.0,
        "supervised_contrastive_weight": 0.05,
        "vicreg_weight": 0,
        "object_readout_adapter": False,
        "object_prompt_balancing": False,
        "reason": "Learn same-name visual clusters; heterogeneous UNKNOWN excluded from SupCon.",
    },
    {
        "name": "iteration3_vicreg",
        "consistency_weight": 1.0,
        "supervised_contrastive_weight": 0,
        "vicreg_weight": 0.01,
        "object_readout_adapter": False,
        "object_prompt_balancing": False,
        "reason": "Check feature invariance with explicit anti-collapse variance and decorrelation.",
    },
    {
        "name": "iteration4_readout_pairs",
        "consistency_weight": 1.0,
        "supervised_contrastive_weight": 0.05,
        "vicreg_weight": 0,
        "object_readout_adapter": True,
        "object_prompt_balancing": False,
        "reason": "Test the zero-appended 74592-parameter whole-frame readout under paired feature training.",
    },
    {
        "name": "iteration5_prompts_consolidation",
        "consistency_weight": 2.0,
        "supervised_contrastive_weight": 0.025,
        "vicreg_weight": 0,
        "object_readout_adapter": "inherit",
        "object_prompt_balancing": True,
        "reason": "Consolidate current champion with independently sampled supported training prompts and stronger consistency.",
    },
)


def main():
    root = Path.cwd()
    source = json.loads((root / "source-manifest.json").read_text(encoding="utf-8"))
    anchors = {
        root / "warm.pt": WARM,
        root / "previous.pt": PREVIOUS_SHA,
        root / "previous-policy.json": POLICY_SHA,
        root / "data/dataset.json": DATA,
    }

    def protect():
        if any(sha(p) != h for p, h in anchors.items()):
            raise ValueError("Own source/weight/data anchors changed")
        if any(sha(root / r["file"]) != r["sha256"] for r in source["files"]):
            raise ValueError("Frozen capsule sources changed")

    protect()
    output = root / "development-v1"
    output.mkdir()
    plan = {
        "schema": 1,
        "trials": TRIALS,
        "steps_each": 10000,
        "learning_rate": 0.00003,
        "round_id": 10981,
        "photo_fraction": 0.65,
        "dataset_sha256": DATA,
        "warm_sha256": WARM,
        "capsule_sha256": sha(root / "capsule.tgz"),
        "production_admitted": False,
        "lineage_rule": "Warm from lowest class/domain-balanced dev CE so far, including initial anchor; rejected iterations never displace champion.",
        "selection": "DEVELOPMENT_ONLY; same score and source cohort in every iteration, not causal ablation or blind exam.",
        "transition": "Dev recall>=.8, no accepted error, UNKNOWN recall>=.9 and each known class>=5 accepted/recall>=.8 are a screening prerequisite ONLY. Then acquire separate fresh sources and run the full unchanged acceptance before moving batch.",
        "limits": "Own weights only; paired views are not independent samples; no calibration/final/textbook inference in training. Prior final is known regression now, never a fresh exam.",
        "literature": [
            "https://arxiv.org/abs/1912.02781",
            "https://arxiv.org/abs/2004.11362",
            "https://arxiv.org/abs/2105.04906",
        ],
        "adaptation": "Small joint CE+feature objectives, not reproduction of full AugMix/SupCon/VICReg ImageNet recipes. JSD uses two full-frame views; no unsafe random crops. No learned projector or external encoder.",
    }
    write_json(output / "plan.json", plan)
    env = dict(
        os.environ,
        PYTHONPATH=str(root / "src") + ":" + str(root / "scripts"),
        AI_BRAIN_CAPSULE_SHA256=plan["capsule_sha256"],
        PYTHONIOENCODING="utf-8",
    )
    # The accepted old core is never a candidate for object accuracy selection.
    import numpy as np
    import torch
    from m33_primary_objects_pilot import (
        ObjectPrepared,
        domain_balanced_loss,
        loss_on,
        probabilities,
    )
    from m33_primary_relations_pilot import Prepared as OldPrepared

    from ai_brain.training import primary_objects as obj
    from ai_brain.training import primary_relations as old

    torch.set_num_threads(2)
    torch.manual_seed(20261009 + 10981)
    model = (
        obj.ObjectsModel.from_checkpoint(
            torch.load(root / "warm.pt", map_location="cpu", weights_only=True)
        )
        .to("cuda")
        .eval()
    )
    manifest = json.loads((root / "data/dataset.json").read_text(encoding="utf-8"))
    dev = ObjectPrepared(
        np.load(root / "data/pixels.npz", allow_pickle=False),
        "dev",
        torch.device("cuda"),
    )
    replay = old.corpus(
        train_scenes=1200, holdout_scenes=300, round_id=10981, legacy_all_aliases=True
    )
    old_dev = OldPrepared(replay["dev"], torch.device("cuda"))
    champion_loss = 0.5 * domain_balanced_loss(
        dev,
        probabilities(model, dev, consensus=False),
        manifest["records"]["dev"],
        class_balanced=True,
    )
    champion_loss += 0.5 * loss_on(
        old_dev, probabilities(model, old_dev, consensus=False)
    )
    write_json(
        output / "initial-anchor-score.json",
        {
            "best_dev_loss": champion_loss,
            "checkpoint_sha256": WARM,
            "round_id": 10981,
            "selection_used": "DEVELOPMENT_ONLY",
        },
    )
    del model, dev, old_dev, replay
    torch.cuda.empty_cache()
    champion_path, champion_arch = root / "warm.pt", False
    reports = []
    for iteration, trial in enumerate(TRIALS, 1):
        readout = (
            champion_arch
            if trial["object_readout_adapter"] == "inherit"
            else trial["object_readout_adapter"]
        )
        # A readout cannot be silently removed; continue it only if promoted.
        readout = readout or champion_arch
        name = trial["name"]
        candidate = output / name
        lineage = {
            "iteration": iteration,
            "name": name,
            "warm_path": str(champion_path),
            "warm_sha256": sha(champion_path),
            "champion_score_before": champion_loss,
            "object_readout_adapter": readout,
            "trial": trial,
            "production_admitted": False,
        }
        write_json(output / (name + "-lineage.json"), lineage)
        args = [
            PYTHON,
            "scripts/m33_primary_objects_pilot.py",
            "--output",
            str(candidate),
            "--data",
            "data",
            "--previous",
            "previous.pt",
            "--previous-policy",
            "previous-policy.json",
            "--warm-start",
            str(champion_path),
            "--device",
            "cuda",
            "--protect-inherited",
            "--object-unknown-adapter",
            "--vision-extension-channels",
            "64",
            "--vision-extension-depth",
            "2",
            "--steps",
            "10000",
            "--eval-every",
            "500",
            "--round-id",
            "10981",
            "--learning-rate",
            ".00003",
            "--illustration-fraction",
            ".65",
            "--diversity-augmentation",
            "--background-augmentation",
            "--domain-balanced-dev",
            "--class-domain-balanced-dev",
            "--development-only",
            "--paired-object-training",
            "--consistency-weight",
            str(trial["consistency_weight"]),
            "--supervised-contrastive-weight",
            str(trial["supervised_contrastive_weight"]),
            "--vicreg-weight",
            str(trial["vicreg_weight"]),
            "--evaluation-note",
            plan["limits"],
        ]
        if readout:
            args.append("--object-readout-adapter")
        if trial["object_prompt_balancing"]:
            args.append("--object-prompt-balancing")
        with (output / (name + ".log")).open("x", encoding="utf-8") as stream:
            code = subprocess.run(
                args, env=env, stdout=stream, stderr=subprocess.STDOUT, check=False
            ).returncode
        print(
            json.dumps({"iteration": iteration, "candidate": name, "exit_code": code}),
            flush=True,
        )
        protect()
        if code:
            raise RuntimeError("Iteration failed: " + name)
        report = json.loads(
            (candidate / "development-report.json").read_text(encoding="utf-8")
        )
        diagnostic_path = root / (name + "-dev-photo.json")
        dev_photos(root / "data", output, diagnostic_path, ("warm", name))
        diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))[
            "candidates"
        ][name]
        rows = [
            dict(r, selected=selected(r["probabilities"], 0.99))
            for r in diagnostic["five_view"]["records"]
        ]
        stats = statistics(rows)
        classes = {
            label: statistics([r for r in rows if r["gold"] == label])
            for label in sorted({r["gold"] for r in rows if r["gold"] != "UNKNOWN"})
        }
        viable = (
            stats["false_assertions"] == 0
            and stats["answerable_recall"] >= 0.8
            and stats["unknown_recall"] >= 0.9
            and len(classes) == 8
            and all(
                r["accepted"] >= 5 and r["answerable_recall"] >= 0.8
                for r in classes.values()
            )
        )
        promoted = report["best_dev_loss"] < champion_loss
        receipt = dict(
            lineage,
            best_step=report["best_step"],
            best_dev_loss=report["best_dev_loss"],
            checkpoint_sha256=sha(candidate / "best.pt"),
            inherited_tensors_byte_preserved=report["inherited_tensors_byte_preserved"],
            fixed_99_five_view_dev=stats,
            by_concept=classes,
            raw_single_view=diagnostic["single_view"]["raw_not_safe_policy"],
            raw_five_view=diagnostic["five_view"]["raw_not_safe_policy"],
            promoted_by_development_loss=promoted,
            dev_screen_viable=viable,
            fresh_acceptance_passed=False,
        )
        write_json(output / (name + "-receipt.json"), receipt)
        reports.append(receipt)
        if promoted:
            champion_path, champion_loss, champion_arch = (
                candidate / "best.pt",
                report["best_dev_loss"],
                readout,
            )
        print(json.dumps(receipt), flush=True)
        if viable:
            write_json(
                root / "fresh-exam-required.json",
                {
                    "iteration": iteration,
                    "checkpoint_sha256": receipt["checkpoint_sha256"],
                    "status": "STOP_FOR_FRESH_SOURCE_EXAM_NOT_ADMITTED",
                },
            )
            return
    selection = {
        "schema": 1,
        "selection_used": "DEVELOPMENT_ONLY",
        "dataset_sha256": DATA,
        "round_id": 10981,
        "iterations": reports,
        "winner": {
            "name": champion_path.parent.name
            if champion_path.name != "warm.pt"
            else "initial_warm",
            "candidate_path": str(champion_path.parent),
            "checkpoint_sha256": sha(champion_path),
            "best_dev_loss": champion_loss,
            "architecture": {
                "vision_extension_channels": 64,
                "vision_extension_depth": 2,
                "object_unknown_adapter": True,
                **({"object_readout_adapter": True} if champion_arch else {}),
            },
        },
        "production_admitted": False,
        "fresh_acceptance_passed": False,
        "limits": plan["limits"],
    }
    write_json(root / "selection-development-only.json", selection)
    protect()
    print(
        json.dumps(
            {
                "completed_iterations": 5,
                "winner": selection["winner"],
                "production_admitted": False,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
