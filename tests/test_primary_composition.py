import numpy as np
import pytest
import torch

from ai_brain.training import primary_composition as c
from ai_brain.training import primary_objects as old
from ai_brain.training import primary_zero as base


@pytest.fixture(scope="module")
def model():
    torch.set_num_threads(2)
    torch.manual_seed(42)
    return c.CompositionModel(old.ObjectsModel(width=32, layers=1)).eval()


def test_renderer_reproducible_and_no_metadata_input():
    scene = c.scenes("train", 1, 123)[0]
    assert c.render(scene).shape == (96, 96, 3)
    assert np.array_equal(c.render(scene), c.render(scene))
    assert c.render(scene).flags.writeable


def test_combinations_really_held_and_no_pixels_shared():
    data = {
        split: c.prepare(c.scenes(split, 12, 2000 + i * 100))
        for i, split in enumerate(
            ("train", "dev", "calibration", "final", "combinations", "transfer")
        )
    }
    assert c.audit(data)["unique_images"] == 72
    data["dev"] = data["train"]
    with pytest.raises(ValueError, match="leakage"):
        c.audit(data)


def test_hidden_parts_are_unknown_not_generic_knowledge():
    scene = c.Scene(
        "test",
        1,
        (
            c.Item("зелёный", "овал", "полосатый", True),
            c.Item("красный", "круг", "однотонный"),
        ),
    )
    assert all(scene.gold(task, 0) == c.UNKNOWN for task in c.VALUES)
    assert scene.gold("color", 1) == c.ANSWERS.index("красный")
    with pytest.raises(ValueError):
        scene.gold("legs", 0)


@pytest.mark.parametrize("task", c.VALUES)
@pytest.mark.parametrize("side", (0, 1))
@pytest.mark.parametrize("template", range(3))
def test_bilingual_queries(task, side, template):
    tokens = c.encode_question(c.question(task, side, template))
    assert len(tokens) == base.QUESTION_LENGTH + 1
    assert tokens[-1] == base.READ_ID


def test_unsupported_description_is_rejected():
    with pytest.raises(ValueError):
        c.encode_question("Жираф сладкий?")
    assert c.describe([c.UNKNOWN] * 6)["object_identity"] == "UNKNOWN"
    with pytest.raises(ValueError):
        c.describe([c.ANSWERS.index("овал")] * 6)


def test_shared_core_gradient_and_old_weights_exact(model):
    original = {k: v.clone() for k, v in model.inherited.state_dict().items()}
    assert sum(isinstance(m, type(model.inherited.core)) for m in model.modules()) == 1
    model.train()
    assert not model.inherited.training
    images = (
        torch.from_numpy(c.render(c.scenes("train", 1, 321)[0]))
        .permute(2, 0, 1)[None]
        .float()
        / 255
    )
    q = torch.tensor([c.encode_question(c.question("pattern", 0))])
    logits = model(images, q)
    torch.nn.functional.cross_entropy(
        logits, torch.tensor([c.ANSWERS.index("однотонный")])
    ).backward()
    assert model.pixel_residual[-1].weight.grad.abs().sum() > 0
    assert model.new_words.weight.grad.abs().sum() > 0
    assert all(p.grad is None for p in model.inherited.parameters())
    assert all(
        torch.equal(v, model.inherited.state_dict()[k]) for k, v in original.items()
    )
    assert not torch.isfinite(logits[0, c.ANSWERS.index("круг")])
    old_q = torch.tensor([old.encode_question(old.OBJECT_QUESTIONS[0])])
    assert torch.equal(
        model.legacy_forward(images, old_q), model.inherited(images, old_q)
    )


def test_invalid_model_inputs(model):
    q = torch.tensor([c.encode_question(c.question("shape", 0))])
    with pytest.raises(ValueError):
        model(torch.full((1, 3, 96, 96), float("nan")), q)
    with pytest.raises(ValueError):
        model(torch.zeros(1, 3, 96, 96), q + 9999)


def test_candidate_roundtrip(model):
    other = c.CompositionModel(old.ObjectsModel(width=32, layers=1))
    other.load_candidate(model.candidate_state())
    assert not any(k.startswith("inherited.") for k in model.candidate_state())
    with pytest.raises(ValueError):
        other.load_candidate({})
    with pytest.raises(ValueError):
        c.CompositionModel(
            old.ObjectsModel(width=32, layers=1), attribute_attention=False
        ).load_candidate(model.candidate_state())


def test_abstention_and_metrics_fail_closed():
    p = np.eye(len(c.ANSWERS))[[0, 0, c.UNKNOWN]]
    assert c.select(p, [None, 0.99, 0.99]) == [c.UNKNOWN, 0, c.UNKNOWN]
    metrics = c.statistics([0, 1, c.UNKNOWN], [c.UNKNOWN, 0, c.UNKNOWN])
    assert metrics["false_assertions"] == 1
    assert metrics["answerable_recall"] == 0
    with pytest.raises(ValueError):
        c.select(p, [-1, 0.99, 0.99])


@pytest.mark.parametrize("style", ("diverse", "challenge"))
def test_diversity_renderer_reproducible(style):
    scene = c.Scene(
        "variant",
        246,
        (
            c.Item("синий", "квадрат", "полосатый"),
            c.Item("зелёный", "овал", "пятнистый"),
        ),
        style,
    )
    assert np.array_equal(c.render(scene), c.render(scene))
    assert c.render(scene).shape == (96, 96, 3)
    other = c.Scene(scene.identity, scene.seed, scene.items, "standard")
    assert not np.array_equal(c.render(scene), c.render(other))


def test_diverse_profile_preserves_holdouts_and_challenge_exclusion():
    groups = {
        split: c.prepare(c.scenes(split, 12, 50000 + i * 1000, profile="diverse"))
        for i, split in enumerate(
            ("train", "dev", "calibration", "final", "combinations", "transfer")
        )
    }
    assert c.audit(groups)["unique_images"] == 72
    assert {s["style"] for s in groups["train"]["scenes"]} == {"standard", "diverse"}
    assert {s["style"] for s in groups["transfer"]["scenes"]} == {"challenge"}
    with pytest.raises(ValueError):
        c.scenes("train", 1, 1, profile="invented")


def test_fully_hidden_diverse_half_has_no_attribute_pixels():
    for style in ("diverse", "challenge"):
        scene = c.Scene(
            "masked",
            99,
            (
                c.Item("белый", "квадрат", "пятнистый", True),
                c.Item("синий", "овал", "полосатый"),
            ),
            style,
        )
        changed = c.Scene(
            scene.identity,
            scene.seed,
            (c.Item("красный", "круг", "однотонный", True), scene.items[1]),
            style,
        )
        # Full cover eliminates all hidden attribute pixels; RNG consumption is
        # deliberately not claimed to be counterfactually identical on the right.
        assert np.array_equal(
            c.render(scene)[10:85, :43], c.render(changed)[10:85, :43]
        )


def test_spatial_append_function_preserving_and_trainable(model):
    expanded = c.CompositionModel(
        old.ObjectsModel(width=32, layers=1), spatial_readout=True
    ).eval()
    expanded.inherited.load_state_dict(model.inherited.state_dict())
    expanded.load_warm_candidate(model.candidate_state())
    pixels = (
        torch.from_numpy(c.render(c.scenes("train", 1, 678, profile="diverse")[0]))
        .permute(2, 0, 1)[None]
        .float()
        / 255
    )
    q = torch.tensor([c.encode_question(c.question("shape", 1))])
    model.eval()
    assert torch.equal(expanded(pixels, q), model(pixels, q))
    expanded.train()
    torch.nn.functional.cross_entropy(
        expanded(pixels, q), torch.tensor([c.ANSWERS.index("круг")])
    ).backward()
    assert expanded.spatial_answer[-1].weight.grad.abs().sum() > 0
    assert all(p.grad is None for p in expanded.inherited.parameters())
    assert (
        sum(isinstance(m, type(model.inherited.core)) for m in expanded.modules()) == 1
    )


def test_spatial_append_strict_warm_keys_and_roundtrip():
    plain = c.CompositionModel(old.ObjectsModel(width=32, layers=1))
    expanded = c.CompositionModel(
        old.ObjectsModel(width=32, layers=1), spatial_readout=True
    )
    with pytest.raises(ValueError, match="Incomplete"):
        expanded.load_candidate(plain.candidate_state())
    with pytest.raises(ValueError, match="Incompatible"):
        expanded.load_warm_candidate({})
    copied = c.CompositionModel(
        old.ObjectsModel(width=32, layers=1), spatial_readout=True
    )
    copied.load_candidate(expanded.candidate_state())
    expanded.spatial_answer[-1].bias.data.fill_(1)
    with pytest.raises(ValueError, match="function preserving"):
        expanded.load_warm_candidate(plain.candidate_state())
    with pytest.raises(ValueError):
        c.CompositionModel(
            old.ObjectsModel(width=32, layers=1),
            attribute_attention=False,
            spatial_readout=True,
        )


@pytest.mark.parametrize("color", ("белый", "чёрный"))
@pytest.mark.parametrize("pattern", ("полосатый", "пятнистый"))
def test_clear_profile_marks_light_and_dark_surfaces_visibly(color, pattern):
    scene = c.Scene(
        "contrast",
        250,
        (c.Item(color, "круг", pattern), c.Item("синий", "квадрат", "однотонный")),
        "diverse_clear",
    )
    plain = c.Scene(
        scene.identity,
        scene.seed,
        (c.Item(color, "круг", "однотонный"), scene.items[1]),
        scene.style,
    )
    difference = np.abs(
        c.render(scene)[:, :45].astype(int) - c.render(plain)[:, :45].astype(int)
    ).max(-1)
    assert (difference > 40).sum() >= 40
    assert scene.gold("pattern", 0) != c.UNKNOWN


def test_shape_edge_view_color_invariance():
    torch.manual_seed(500)
    pixels = torch.rand(2, 3, 96, 96)
    edge = c.shape_edge_pixels(pixels)
    assert edge.shape == pixels.shape
    assert torch.allclose(edge, c.shape_edge_pixels(pixels[:, [2, 0, 1]]), atol=1e-6)
    assert torch.allclose(edge, c.shape_edge_pixels(1 - pixels), atol=1e-6)


def test_rotated_geometry_bound_has_positive_border_and_half_plane_clearance():
    bounding_radius = np.sqrt(2) * c.DIVERSE_MAX_RADIUS
    assert bounding_radius < 24 - c.DIVERSE_CENTER_JITTER
    assert 31 - bounding_radius > 0
    assert 65 + bounding_radius < 96


def test_shape_preprocessing_does_not_change_color_or_legacy_forward():
    plain = c.CompositionModel(
        old.ObjectsModel(width=32, layers=1), spatial_readout=True
    ).eval()
    edges = c.CompositionModel(
        old.ObjectsModel(width=32, layers=1), spatial_readout=True, shape_edges=True
    ).eval()
    edges.inherited.load_state_dict(plain.inherited.state_dict())
    edges.load_candidate(plain.candidate_state())
    pixels = (
        torch.from_numpy(
            c.render(c.scenes("train", 1, 579, profile="diverse_clear")[0])
        )
        .permute(2, 0, 1)[None]
        .float()
        / 255
    )
    color_q = torch.tensor([c.encode_question(c.question("color", 1))])
    assert torch.equal(edges(pixels, color_q), plain(pixels, color_q))
    shape_q = torch.tensor([c.encode_question(c.question("shape", 1))])
    assert torch.allclose(
        edges(pixels, shape_q), edges(pixels[:, [2, 0, 1]], shape_q), atol=1e-6
    )
    legacy_q = torch.tensor([old.encode_question(old.OBJECT_QUESTIONS[0])])
    assert torch.equal(
        edges.legacy_forward(pixels, legacy_q), plain.legacy_forward(pixels, legacy_q)
    )


def test_clear_profile_holds_out_waves_and_irregular_spots():
    train = c.scenes("train", 20, 32100, profile="diverse_clear")
    transfer = c.scenes("transfer", 20, 33100, profile="diverse_clear")
    assert {s.style for s in train} == {"diverse_clear"}
    assert {s.style for s in transfer} == {"challenge_clear"}


def test_split_audit_checks_seeds_even_when_different_rendering_hides_pixel_match():
    train = c.prepare(c.scenes("train", 2, 50100, profile="legacy"))
    dev = c.prepare(c.scenes("dev", 2, 50100, profile="diverse_clear"))
    assert train["records"][0]["image_sha256"] != dev["records"][0]["image_sha256"]
    with pytest.raises(ValueError, match="seed leakage"):
        c.audit({"train": train, "dev": dev})


def test_split_audit_checks_scene_identity_and_reports_distinct_seed_count():
    train = c.prepare(c.scenes("train", 2, 50200))
    dev = c.prepare(c.scenes("dev", 2, 50300))
    good = c.audit({"train": train, "dev": dev})
    assert good["unique_scene_seeds"] == good["unique_scene_identities"] == 4
    dev["scenes"][0]["identity"] = train["scenes"][0]["identity"]
    with pytest.raises(ValueError, match="identity leakage"):
        c.audit({"train": train, "dev": dev})


@pytest.mark.parametrize(
    "seed,digest",
    (
        (
            1103610000,
            "267e7b21fd515a7ba03134011a82cf944de23752ae23a22764a1396f5cb42762",
        ),
        (
            1200310000,
            "1c78071da228fa0991a809ff71e742d4dd7d3189094ef6f87952c4b6f9858852",
        ),
    ),
)
def test_background_probe_option_preserves_default_pixels(seed, digest):
    import hashlib

    row = c.scenes("dev", 1, seed, profile="diverse_clear", independent_labels=False)[0]
    assert hashlib.sha256(c.render_diverse(row).tobytes()).hexdigest() == digest
    assert not np.array_equal(
        c.render_diverse(row),
        c.render_diverse(row, background_override=(225, 225, 225)),
    )


def test_background_probe_changes_no_opaque_surface_pixels():
    scene = c.Scene(
        "paired-background",
        150,
        (
            c.Item("красный", "квадрат", "однотонный"),
            c.Item("синий", "круг", "однотонный"),
        ),
        "diverse_clear",
    )
    a = c.render_diverse(scene, background_override=(45, 45, 45))
    b = c.render_diverse(scene, background_override=(225, 225, 225))
    # Deep inside the exactly same opaque foreground RGB pixels are equal.
    red = (a[..., 0] > 180) & (a[..., 1] < 70) & (a[..., 2] < 70)
    blue = (a[..., 2] > 180) & (a[..., 0] < 60) & (a[..., 1] < 110)
    same = (a == b).all(-1)
    assert (same & red).sum() >= 100 and (same & blue).sum() >= 100
    for bad in ((1, 2), (1, 2, float("nan")), (1, 2, 256)):
        with pytest.raises(ValueError, match="background"):
            c.render_diverse(scene, background_override=bad)


def test_label_render_rng_domains_remove_the_reproduced_background_shortcut():
    from ai_brain.training.primary_composition_rng_audit import audit

    archival = audit(seed=55150000, independent_labels=False)
    fixed = audit(seed=55150000)
    assert archival["background_only_pattern_accuracy"] == [1.0, 1.0]
    assert archival["confusion_gold_by_background_prediction"] == [
        [[3396, 0, 0], [0, 3307, 0], [0, 0, 3297]],
        [[3352, 0, 0], [0, 3353, 0], [0, 0, 3295]],
    ]
    assert not archival["known_shortcut_absent"]
    assert fixed["known_shortcut_absent"]
    assert all(0.30 < a < 0.38 for a in fixed["background_only_pattern_accuracy"])
    assert c.scenes("train", 5, 18000) == c.scenes("train", 5, 18000)
    assert c.scenes("train", 5, 18000) != c.scenes(
        "train", 5, 18000, independent_labels=False
    )
    with pytest.raises(ValueError, match="Invalid corpus"):
        c.scenes("train", 5, 18000, independent_labels=1)
