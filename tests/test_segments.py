from __future__ import annotations

import torch

from ai_brain.segments import (
    SEG_ANSWER,
    SEG_CONTEXT,
    SEG_CONTROL,
    SEG_QUERY,
    SEG_WORKSPACE,
    build_segment_attention_allow_mask,
)


def test_query_isolated_blocks_context_from_query_and_answer() -> None:
    segment_ids = torch.tensor(
        [[SEG_CONTROL, SEG_CONTEXT, SEG_QUERY, SEG_ANSWER]],
        dtype=torch.long,
    )

    mask = build_segment_attention_allow_mask(
        segment_ids,
        mode="query_isolated",
    )

    assert mask is not None
    assert bool(mask[0, 2, 1]) is False
    assert bool(mask[0, 2, 2]) is True
    assert bool(mask[0, 3, 1]) is False
    assert bool(mask[0, 3, 2]) is True
    assert bool(mask[0, 3, 3]) is True


def test_workspace_allows_only_accessible_context_to_workspace() -> None:
    segment_ids = torch.tensor(
        [[SEG_CONTROL, SEG_CONTEXT, SEG_CONTEXT, SEG_QUERY, SEG_WORKSPACE, SEG_ANSWER]],
        dtype=torch.long,
    )
    access = torch.tensor([[0, 1, 0, 0, 0, 0]], dtype=torch.long)

    mask = build_segment_attention_allow_mask(
        segment_ids,
        mode="workspace",
        context_access_mask=access,
    )

    assert mask is not None
    assert bool(mask[0, 4, 1]) is True
    assert bool(mask[0, 4, 2]) is False
    assert bool(mask[0, 5, 1]) is True
    assert bool(mask[0, 5, 2]) is False
    assert bool(mask[0, 5, 4]) is True
