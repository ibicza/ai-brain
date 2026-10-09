"""Rights, partition and full-background dedup regressions for photo admission."""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from m33_objects_photo_prepare import photo_aware_families
from m33_objects_photos import author_owner, rights
from m33_primary_objects_pilot import domain_balanced_loss


def test_author_has_one_owner_across_html_alias_formatting():
    assert author_owner('<a href="x">Alice</a>') == author_owner(" alice ")
    with pytest.raises(ValueError):
        author_owner("<div></div>")


@pytest.mark.parametrize(
    "name", ["CC BY-NC 4.0", "CC BY-ND 4.0", "GFDL", "Copyrighted", ""]
)
def test_unclear_or_restricted_rights_not_admitted(name):
    with pytest.raises(ValueError):
        rights({"LicenseShortName": {"value": name}, "Artist": {"value": "Author"}})


def test_rights_bind_official_license_url_and_artist():
    meta = {
        "LicenseShortName": {"value": "CC BY-SA 4.0"},
        "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"},
        "Artist": {"value": "Author"},
    }
    assert rights(meta)[0] == "CC BY-SA 4.0"
    meta["LicenseUrl"]["value"] = "https://creativecommons.org/licenses/by-sa/3.0"
    with pytest.raises(ValueError):
        rights(meta)
    meta["LicenseUrl"]["value"] = "https://creativecommons.org/licenses/by/4.0"
    with pytest.raises(ValueError):
        rights(meta)
    meta["LicenseUrl"]["value"] = "https://example.org/licenses/by-sa/4.0"
    with pytest.raises(ValueError):
        rights(meta)


def test_unrelated_full_background_photos_not_mask_duplicates():
    colors = [
        np.full((96, 96, 3), 30, dtype=np.uint8),
        np.full((96, 96, 3), 180, dtype=np.uint8),
    ]
    roles = [{"role": "VISUALLY_CURATED_NONBLIND_PHOTOGRAPH"}] * 2
    groups = photo_aware_families(colors, roles)
    assert groups[0] != groups[1]


def test_mirrored_photos_remain_same_family():
    image = np.full((96, 96, 3), 30, dtype=np.uint8)
    image[20:50, 10:35] = 180
    roles = [{"role": "VISUALLY_CURATED_NONBLIND_PHOTOGRAPH"}] * 2
    groups = photo_aware_families([image, image[:, ::-1].copy()], roles)
    assert groups[0] == groups[1]


def test_dev_domain_loss_does_not_ignore_rare_photo_domain():
    data = SimpleNamespace(answers=torch.zeros(11, dtype=torch.long))
    records = [{"role": "VISUALLY_CURATED_NONBLIND_SCHEMATIC_LABEL"}] * 10 + [
        {"role": "VISUALLY_CURATED_NONBLIND_PHOTOGRAPH"}
    ]
    probs = [[0.9, 0.1]] * 10 + [[0.1, 0.9]]
    assert domain_balanced_loss(data, probs, records) == pytest.approx(
        (-np.log(0.9) - np.log(0.1)) / 2
    )
    with pytest.raises(ValueError):
        domain_balanced_loss(data, probs, records[:-1])
