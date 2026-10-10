"""Independent read/reassembly of frozen real-source control tensors and gold."""

import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load(folder, c):
    receipt = read(folder / "preparation-receipt.json")
    freeze = read(folder / "preparation-freeze.json")
    if (
        receipt["status"] != "SOURCE_CONTROL_TENSORS_PREPARED_NOT_EVALUATED"
        or receipt["training_or_calibration"]
        or receipt["production_admitted"]
        or freeze["training_or_calibration"]
        or freeze["production_admitted"]
        or receipt["answers"] != list(c.ANSWERS)
        or freeze["answers"] != list(c.ANSWERS)
    ):
        raise ValueError("Frozen no-fitting source preparation required")
    expected = {
        "source-annotations.json": receipt["annotation_manifest_sha256"],
        "dataset.npz": receipt["dataset_sha256"],
        "records.json.gz": receipt["records_sha256"],
        "source-crops.npz": receipt["source_crops_sha256"],
        "preparation-freeze.json": receipt["preparation_freeze_sha256"],
        "preparation-executed.py": freeze["preparation_source_sha256"],
    }
    if (
        any(sha(folder / name) != digest for name, digest in expected.items())
        or sha(Path(c.__file__)) != freeze["course_source_sha256"]
    ):
        raise ValueError("Source preparation bytes/vocabulary implementation changed")
    with np.load(folder / "dataset.npz", allow_pickle=False) as archive:
        if set(archive.files) != {
            "source_" + key for key in ("pixels", "questions", "labels", "image_index")
        }:
            raise ValueError("Source array contract differs")
        data = {
            key: archive["source_" + key]
            for key in ("pixels", "questions", "labels", "image_index")
        }
    with gzip.open(folder / "records.json.gz", "rt", encoding="utf-8") as stream:
        meta = json.load(stream)
    annotations = meta["annotation_manifest"]
    if (
        annotations != read(folder / "source-annotations.json")
        or freeze["annotation_manifest_sha256"] != receipt["annotation_manifest_sha256"]
        or annotations["training_admitted"]
        or annotations["evaluation"]["training_or_calibration"]
    ):
        raise ValueError("Original annotation manifest differs")
    assets = meta["assets"]
    original_assets = annotations["assets"]
    if (
        len(assets) != len(original_assets)
        or len({a["id"] for a in assets}) != len(assets)
        or len(assets) != receipt["unique_source_assets"]
    ):
        raise ValueError("Source asset correspondence differs")
    for asset, original in zip(assets, original_assets, strict=True):
        if {k: asset[k] for k in original} != original:
            raise ValueError("Source annotations differ from manifest")
    with np.load(folder / "source-crops.npz", allow_pickle=False) as archive:
        if set(archive.files) != {f"asset_{i:03d}" for i in range(len(assets))}:
            raise ValueError("Source crop inventory differs")
        crops = [archive[f"asset_{i:03d}"] for i in range(len(assets))]
    for asset, crop in zip(assets, crops, strict=True):
        if (
            crop.dtype != np.uint8
            or crop.ndim != 3
            or crop.shape[-1] != 3
            or list(crop.shape[1::-1]) != asset["crop_size"]
            or hashlib.sha256(crop.tobytes()).hexdigest() != asset["crop_rgb_sha256"]
        ):
            raise ValueError("Source original crop pixels differ")
    count = len(assets) * (len(assets) - 1)
    if (
        data["pixels"].dtype != np.uint8
        or data["pixels"].shape != (count, 96, 96, 3)
        or data["questions"].dtype != np.int64
        or data["questions"].shape != (count * 6, 13)
        or data["labels"].dtype != np.int64
        or data["image_index"].dtype != np.int64
        or data["labels"].shape != (count * 6,)
        or data["image_index"].shape != (count * 6,)
        or len(meta["records"]) != count * 6
        or len(meta["scenes"]) != count
    ):
        raise ValueError("Source scene/question dimensions differ")
    index = 0
    for left in range(len(assets)):
        for right in range(len(assets)):
            if left == right:
                continue
            image = np.full((96, 96, 3), 255, dtype=np.uint8)
            identity = f"real-source/{assets[left]['id']}+{assets[right]['id']}"
            expected_scene = {
                "identity": identity,
                "asset_ids": [assets[left]["id"], assets[right]["id"]],
            }
            if meta["scenes"][index] != expected_scene:
                raise ValueError("Source pairing correspondence differs")
            for side, selected in enumerate((left, right)):
                view = Image.fromarray(crops[selected])
                view.thumbnail((32, 32), Image.Resampling.LANCZOS)
                x, y = (24, 72)[side] - view.width // 2, 48 - view.height // 2
                image[y : y + view.height, x : x + view.width] = np.asarray(view)
                view.close()
            if not np.array_equal(image, data["pixels"][index]):
                raise ValueError("Source compositor does not replay exact crop pixels")
            digest = hashlib.sha256(image.tobytes()).hexdigest()
            for side, selected in enumerate((left, right)):
                asset = assets[selected]
                for task_index, task in enumerate(c.VALUES):
                    row_index = index * 6 + side * 3 + task_index
                    query = c.question(task, side, index % 3)
                    value = asset[task]
                    gold = (
                        c.UNKNOWN
                        if asset["absent"] or value not in c.VALUES[task]
                        else c.ANSWERS.index(value)
                    )
                    expected_row = {
                        "scene_id": identity,
                        "image_sha256": digest,
                        "task": task,
                        "side": side,
                        "question": query,
                        "answer": gold,
                        "source_asset_id": asset["id"],
                    }
                    if (
                        meta["records"][row_index] != expected_row
                        or data["labels"][row_index] != gold
                        or data["image_index"][row_index] != index
                        or not np.array_equal(
                            data["questions"][row_index], c.encode_question(query)
                        )
                    ):
                        raise ValueError(
                            "Source question/gold/pixel correspondence differs"
                        )
            index += 1
    data.update({"records": meta["records"], "scenes": meta["scenes"]})
    hashes = {
        str(folder / name): sha(folder / name)
        for name in (*expected, "preparation-receipt.json")
    }
    return data, tuple(asset["id"] for asset in assets), hashes, receipt
