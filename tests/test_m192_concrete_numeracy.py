from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "m192_concrete_numeracy.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("m192_concrete_numeracy", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_quantity_surface_keeps_count_structurally_visible() -> None:
    m192 = _load_module()

    assert m192.quantity_surface(0, "X", "space") == "EMPTY"
    assert m192.quantity_surface(3, "X", "space") == "ITEM X ITEM X ITEM X"
    assert m192.quantity_surface(3, "A", "bar") == "ITEM A | ITEM A | ITEM A"
    assert len(m192._object_spans("ITEM X ITEM X ITEM X", "X")) == 3


def test_tokenization_audit_has_no_single_aggregate_stick_tokens() -> None:
    m192 = _load_module()

    rows = m192.tokenization_audit()

    assert rows
    assert not any(row["single_aggregate_token"] for row in rows)
    assert all(
        row["object_span_count"] == row["tokenized_object_span_count"]
        for row in rows
        if row["count"] > 0
    )


def test_m192_splits_have_heldout_objects_and_no_prompt_intersection() -> None:
    m192 = _load_module()
    rng = m192.random.Random(m192.SEED)
    eval_splits = m192._build_eval_splits()
    eval_prompts = {
        str(example["prompt"])
        for examples in eval_splits.values()
        for example in examples
    }
    concept_pools = m192._build_concept_pools(rng, blocked_prompts=eval_prompts)
    final_symbolic = m192._build_final_symbolic_train(
        rng,
        count=200,
        blocked_prompts=eval_prompts,
    )
    curricula = {
        "direct_symbolic": m192._repeat_to_count(final_symbolic, 300),
        "concrete_sequential": m192._repeat_to_count(
            concept_pools["concrete"] + concept_pools["base10"] + final_symbolic,
            300,
        ),
    }

    intersections = m192._prompt_intersections(curricula, eval_splits)
    heldout_count_audit = m192._audit_examples(eval_splits["count_heldout_object"])

    assert max(intersections.values()) == 0
    assert set(heldout_count_audit["object_families"]) == set(m192.HELDOUT_OBJECTS)


def test_linux_runner_contains_no_password_literal() -> None:
    runner = (
        Path(__file__).resolve().parents[1] / "scripts" / "linux" / "run_m192.sh"
    ).read_text(encoding="utf-8")

    assert "mapro" not in runner.lower()
    assert "password" not in runner.lower()
