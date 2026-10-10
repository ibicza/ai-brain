"""Tiny end-to-end train/freeze/replay and hostile receipt modifications."""

import gzip
import importlib.util
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

from ai_brain.training import primary_objects as old


def script(name):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).parents[1] / "scripts" / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pilot = script("m33_primary_composition_pilot")
verifier = script("m33_composition_verify")


@pytest.fixture(
    scope="module",
    params=(0, 1, 2, 3, 4, 5, 6, 7),
    ids=(
        "single-view",
        "four-view",
        "exposure",
        "diverse-exposure",
        "ieee-exposure",
        "ieee-wide-background",
        "ieee-quadratic-background",
        "ieee-rich-palette",
    ),
)
def sealed(tmp_path_factory, request):
    root = tmp_path_factory.mktemp("composition-pipeline")
    torch.manual_seed(500)
    prior = old.ObjectsModel(width=32, layers=1)
    previous = root / "previous.pt"
    torch.save(
        {
            "model": prior.state_dict(),
            "width": 32,
            "layers": 1,
            "compatible_legacy_vocabulary": True,
        },
        previous,
    )
    capsule = root / "source-capsule.tgz"
    probe = root / "source-probe.txt"
    probe.write_text("sealed fixture, not a real source capsule", encoding="utf-8")
    manifest = {
        "schema": 1,
        "files": [{"file": probe.name, "sha256": verifier.sha(probe)}],
    }
    (root / "source-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with tarfile.open(capsule, "w:gz") as archive:
        archive.add(probe, arcname=probe.name)
        archive.add(root / "source-manifest.json", arcname="source-manifest.json")
    # The monkeypatch context must not escape this module-scoped setup.
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("AI_BRAIN_CAPSULE_SHA256", verifier.sha(capsule))
        pilot.run(
            SimpleNamespace(
                output=root / "experiment",
                spatial_readout=False,
                shape_edges=False,
                label_smoothing=0.0,
                reflection_consensus=request.param > 0,
                auxiliary_images=12 if request.param >= 2 else 0,
                consistency_loss=0.2 if request.param >= 2 else 0.0,
                exposure_profile="palette"
                if request.param == 7
                else "diverse"
                if request.param >= 3
                else "standard",
                numeric_precision="ieee" if request.param >= 4 else "legacy",
                previous=previous,
                warm_candidate=None,
                dataset_profile=(
                    "rich_curve_background_clear"
                    if request.param == 7
                    else "curve_background_clear"
                    if request.param == 6
                    else "background_clear"
                    if request.param == 5
                    else "diverse"
                ),
                seed=12000,
                steps=2,
                eval_every=2,
                train_images=12,
                holdout_images=12,
                device="cpu",
            )
        )
    return root


def check(root, name):
    verifier.verify(
        root / "experiment",
        root / "previous.pt",
        root / "source-capsule.tgz",
        root / name,
        "cpu",
    )


def test_rng_audit_cannot_be_rewritten(sealed):
    path = sealed / "experiment/rng-independence-audit.json"
    original = path.read_bytes()
    try:
        changed = json.loads(original)
        changed["background_only_pattern_accuracy"] = [0.0, 0.0]
        path.write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(ValueError, match="RNG leakage audit differs"):
            check(sealed, "must-not-exist-rng.json")
        assert not (sealed / "must-not-exist-rng.json").exists()
    finally:
        path.write_bytes(original)


@pytest.mark.parametrize("reseal", (False, True))
def test_quadratic_policy_cannot_be_rewritten(sealed, reseal):
    path = sealed / "experiment/protocol.json"
    freeze_path = sealed / "experiment/candidate-freeze.json"
    original, frozen_original = path.read_bytes(), freeze_path.read_bytes()
    protocol = json.loads(original)
    if protocol["dataset_profile"] not in (
        "curve_background_clear",
        "rich_curve_background_clear",
    ):
        return
    try:
        protocol["curve_rng_policy"] = "same generator reused for labels"
        path.write_text(json.dumps(protocol), encoding="utf-8")
        if reseal:
            freeze = json.loads(frozen_original)
            freeze["protocol_sha256"] = verifier.sha(path)
            freeze_path.write_text(json.dumps(freeze), encoding="utf-8")
        expected = (
            (
                "Rich curve exposure RNG policy differs"
                if protocol["dataset_profile"] == "rich_curve_background_clear"
                else "Quadratic exposure RNG policy differs"
            )
            if reseal
            else "Frozen inputs/status changed"
        )
        with pytest.raises(ValueError, match=expected):
            check(sealed, "must-not-exist-curve.json")
        assert not (sealed / "must-not-exist-curve.json").exists()
    finally:
        path.write_bytes(original)
        freeze_path.write_bytes(frozen_original)


def test_exact_inference_and_arithmetic_replay(sealed):
    check(sealed, "verified.json")
    report = json.loads((sealed / "verified.json").read_text())
    assert report["status"] == "INFERENCE_AND_ARITHMETIC_VERIFIED"
    assert report["blank_inference_replayed"]
    assert report["question_and_oracle_correspondence_verified"]
    assert not report["production_admitted"]


def test_replay_pre_spatial_constructor_without_source_rewrite(sealed, monkeypatch):
    current = verifier.c.CompositionModel

    def pre_spatial(inherited, *, attribute_attention=True):
        return current(inherited, attribute_attention=attribute_attention)

    monkeypatch.setattr(verifier.c, "CompositionModel", pre_spatial)
    check(sealed, "verified-pre-spatial.json")
    assert (sealed / "verified-pre-spatial.json").exists()


def test_dataset_archive_expands_each_array_only_once(sealed, monkeypatch):
    original_load = verifier.np.load
    accessed = {}

    class CountedArchive:
        def __init__(self, archive):
            self.archive = archive
            self.files = archive.files

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.archive.close()

        def __getitem__(self, key):
            accessed[key] = accessed.get(key, 0) + 1
            return self.archive[key]

    monkeypatch.setattr(
        verifier.np,
        "load",
        lambda *args, **kwargs: CountedArchive(original_load(*args, **kwargs)),
    )
    check(sealed, "verified-single-decompression.json")
    auxiliary = verifier.read(sealed / "experiment/protocol.json").get(
        "auxiliary_images", 0
    )
    assert len(accessed) == (40 if auxiliary else 24)
    assert set(accessed.values()) == {1}


def test_source_manifest_cannot_be_rewritten_alongside_source(sealed):
    path = sealed / "source-manifest.json"
    original = path.read_bytes()
    try:
        path.write_text(json.dumps({"schema": 1, "files": []}), encoding="utf-8")
        with pytest.raises(ValueError, match="sealed capsule"):
            check(sealed, "must-not-exist-source.json")
        assert not (sealed / "must-not-exist-source.json").exists()
    finally:
        path.write_bytes(original)


@pytest.mark.parametrize("field", ("answerable_recall", "false_assertions"))
def test_report_metric_tamper_rejected(sealed, field):
    path = sealed / "experiment/result.json"
    original = path.read_bytes()
    try:
        report = json.loads(original)
        report["reports"]["final"]["selected"]["overall"][field] += 1
        path.write_text(json.dumps(report), encoding="utf-8")
        with pytest.raises(ValueError, match="Metric mismatch"):
            check(sealed, "must-not-exist-" + field + ".json")
    finally:
        path.write_bytes(original)


def test_raw_task_metric_tamper_rejected(sealed):
    path = sealed / "experiment/result.json"
    original = path.read_bytes()
    try:
        report = json.loads(original)
        report["reports"]["final"]["raw_argmax"]["tasks"]["shape"]["accepted"] += 1
        path.write_text(json.dumps(report), encoding="utf-8")
        with pytest.raises(ValueError, match="Metric mismatch"):
            check(sealed, "must-not-exist-raw.json")
    finally:
        path.write_bytes(original)


def test_blank_image_result_is_recomputed_not_trusted(sealed):
    path = sealed / "experiment/blank-image-ablation.json"
    original = path.read_bytes()
    try:
        report = json.loads(original)
        report["overall"]["accepted"] += 1
        path.write_text(json.dumps(report), encoding="utf-8")
        with pytest.raises(ValueError, match="Metric mismatch"):
            check(sealed, "must-not-exist-blank.json")
    finally:
        path.write_bytes(original)


@pytest.mark.parametrize(
    "field,value", (("checkpoint_sha256", "forged"), ("winner", "forged"))
)
def test_result_lineage_tamper_rejected(sealed, field, value):
    path = sealed / "experiment/result.json"
    original = path.read_bytes()
    try:
        report = json.loads(original)
        report[field] = value
        path.write_text(json.dumps(report), encoding="utf-8")
        with pytest.raises(ValueError, match="lineage metadata"):
            check(sealed, "must-not-exist-lineage-" + field + ".json")
    finally:
        path.write_bytes(original)


def test_result_threshold_tamper_rejected(sealed):
    path = sealed / "experiment/result.json"
    original = path.read_bytes()
    try:
        report = json.loads(original)
        report["thresholds"]["shape"] = 0.5
        path.write_text(json.dumps(report), encoding="utf-8")
        with pytest.raises(ValueError, match="thresholds differ"):
            check(sealed, "must-not-exist-threshold.json")
    finally:
        path.write_bytes(original)


def test_smoothing_does_not_average_masked_negative_infinity():
    logits = torch.tensor([[2.0, 1.0, float("-inf")]], requires_grad=True)
    labels = torch.tensor([0])
    loss = pilot.masked_smoothing_loss(logits, labels, 0.02)
    assert torch.isfinite(loss)
    loss.backward()
    assert torch.isfinite(logits.grad).all()
    assert logits.grad[0, 2] == 0
    assert torch.equal(
        pilot.masked_smoothing_loss(logits, labels, 0),
        torch.nn.functional.cross_entropy(logits, labels),
    )
    with pytest.raises(ValueError):
        pilot.masked_smoothing_loss(logits, torch.tensor([2]), 0.02)
    with pytest.raises(ValueError):
        pilot.masked_smoothing_loss(logits, labels, float("nan"))


def test_record_question_target_tamper_rejected(sealed):
    path = sealed / "experiment/dataset-records.json.gz"
    freeze_path = sealed / "experiment/candidate-freeze.json"
    original, original_freeze = path.read_bytes(), freeze_path.read_bytes()
    try:
        records = json.loads(gzip.decompress(original))
        records["final"]["records"][0]["side"] = (
            1 - records["final"]["records"][0]["side"]
        )
        path.write_bytes(gzip.compress(json.dumps(records).encode()))
        freeze = json.loads(original_freeze)
        freeze["records_sha256"] = verifier.sha(path)
        freeze_path.write_text(json.dumps(freeze), encoding="utf-8")
        with pytest.raises(ValueError, match="correspondence"):
            check(sealed, "must-not-exist-target.json")
    finally:
        path.write_bytes(original)
        freeze_path.write_bytes(original_freeze)


def test_single_view_evidence_cannot_be_replaced_with_consensus(sealed):
    path = sealed / "experiment/final-predictions.json.gz"
    original = path.read_bytes()
    try:
        report = json.loads(gzip.decompress(original))
        report["single_view_raw_predictions"][0] = (
            report["single_view_raw_predictions"][0] + 1
        ) % len(pilot.course.ANSWERS)
        path.write_bytes(gzip.compress(json.dumps(report).encode()))
        with pytest.raises(ValueError, match="Single-view inference"):
            check(sealed, "must-not-exist-single-view.json")
    finally:
        path.write_bytes(original)


def test_reflection_policy_result_tampering_is_rejected(sealed):
    path = sealed / "experiment/result.json"
    original = path.read_bytes()
    try:
        report = json.loads(original)
        report["reflection_consensus"] = not report["reflection_consensus"]
        path.write_text(json.dumps(report), encoding="utf-8")
        with pytest.raises(ValueError, match="Reflection policy"):
            check(sealed, "must-not-exist-reflection.json")
    finally:
        path.write_bytes(original)


def test_js_handles_unsupported_classes_and_has_finite_gradient():
    a = torch.tensor([[2.0, 1.0, float("-inf")]], requires_grad=True)
    b = torch.tensor([[1.0, 2.0, float("-inf")]], requires_grad=True)
    loss = pilot.consistency_loss(a, b)
    assert 0 < loss < 0.7
    assert pilot.consistency_loss(a, a) == 0
    loss.backward()
    assert torch.isfinite(a.grad).all() and torch.isfinite(b.grad).all()
    assert a.grad[0, 2] == b.grad[0, 2] == 0
    with pytest.raises(ValueError, match="scope"):
        pilot.consistency_loss(a, torch.tensor([[1.0, float("-inf"), 2.0]]))


def test_join_keeps_pixels_aligned_with_original_queries():
    a = pilot.course.prepare(pilot.course.scenes("calibration", 2, 770100))
    b = pilot.controls.prepare(
        pilot.controls.scenes("exposure", 2, 780100, cohort="control_calibration")
    )
    both = pilot.join_data(a, b)
    assert len(both["pixels"]) == 4 and len(both["labels"]) == 24
    assert both["image_index"].tolist() == [0] * 6 + [1] * 6 + [2] * 6 + [3] * 6
    assert both["records"][:12] == a["records"] and both["records"][12:] == b["records"]


def test_numeric_metadata_cannot_change_between_protocol_and_result(sealed):
    path = sealed / "experiment/result.json"
    original = path.read_bytes()
    try:
        report = json.loads(original)
        report["numeric_backend"]["precision_settings"]["cudnn_conv"] = "forged"
        path.write_text(json.dumps(report), encoding="utf-8")
        with pytest.raises(ValueError, match="Result numeric precision"):
            check(sealed, "must-not-exist-numeric.json")
    finally:
        path.write_bytes(original)


def test_exposure_family_metadata_cannot_be_forged(sealed):
    path = sealed / "experiment/protocol.json"
    freeze_path = sealed / "experiment/candidate-freeze.json"
    original, frozen_original = path.read_bytes(), freeze_path.read_bytes()
    if not json.loads(original)["auxiliary_images"]:
        pytest.skip("No auxiliary cohorts in this fixture")
    try:
        protocol = json.loads(original)
        protocol["exposure_shapes"].append("pentagon")
        path.write_text(json.dumps(protocol), encoding="utf-8")
        freeze = json.loads(frozen_original)
        freeze["protocol_sha256"] = verifier.sha(path)
        freeze_path.write_text(json.dumps(freeze), encoding="utf-8")
        with pytest.raises(ValueError, match="Exposure families"):
            check(sealed, "must-not-exist-families.json")
    finally:
        path.write_bytes(original)
        freeze_path.write_bytes(frozen_original)
