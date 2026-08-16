from __future__ import annotations

from typing import Literal

import torch

SEG_PAD = 0
SEG_CONTEXT = 1
SEG_QUERY = 2
SEG_WORKSPACE = 3
SEG_ANSWER = 4
SEG_CONTROL = 5

SEGMENT_IDS: dict[str, int] = {
    "pad": SEG_PAD,
    "context": SEG_CONTEXT,
    "query": SEG_QUERY,
    "workspace": SEG_WORKSPACE,
    "answer": SEG_ANSWER,
    "control": SEG_CONTROL,
}
SEGMENT_NAMES: dict[int, str] = {value: key for key, value in SEGMENT_IDS.items()}

SegmentAttentionMode = Literal["flat_causal", "query_isolated", "workspace"]
SEGMENT_ATTENTION_MODES: tuple[SegmentAttentionMode, ...] = (
    "flat_causal",
    "query_isolated",
    "workspace",
)


def build_segment_attention_allow_mask(
    segment_ids: torch.Tensor,
    *,
    mode: SegmentAttentionMode,
    context_access_mask: torch.Tensor | None = None,
) -> torch.Tensor | None:
    """Return a [batch, query_seq, key_seq] boolean routing mask.

    The causal mask is still applied inside attention. This mask only expresses
    cross-segment routing rules.
    """

    if mode == "flat_causal":
        return None
    if mode not in SEGMENT_ATTENTION_MODES:
        raise ValueError(f"Unknown segment attention mode: {mode}")
    if segment_ids.ndim != 2:
        raise ValueError("segment_ids must have shape [batch, seq]")

    query_segments = segment_ids.unsqueeze(2)
    key_segments = segment_ids.unsqueeze(1)

    control_key = key_segments == SEG_CONTROL
    query_key = key_segments == SEG_QUERY
    workspace_key = key_segments == SEG_WORKSPACE
    answer_key = key_segments == SEG_ANSWER
    context_key = key_segments == SEG_CONTEXT

    context_query = query_segments == SEG_CONTEXT
    query_query = query_segments == SEG_QUERY
    workspace_query = query_segments == SEG_WORKSPACE
    answer_query = query_segments == SEG_ANSWER
    control_query = query_segments == SEG_CONTROL
    pad_query = query_segments == SEG_PAD

    allow = torch.zeros(
        (*segment_ids.shape, segment_ids.shape[1]),
        dtype=torch.bool,
        device=segment_ids.device,
    )

    allow = torch.where(control_query, control_key, allow)
    allow = torch.where(context_query, control_key | context_key, allow)
    allow = torch.where(query_query, control_key | query_key, allow)

    if mode == "query_isolated":
        allow = torch.where(answer_query, control_key | query_key | answer_key, allow)
        allow = torch.where(
            workspace_query,
            control_key | query_key | workspace_key,
            allow,
        )
    else:
        visible_context_key = _visible_context_key(
            context_key=context_key,
            context_access_mask=context_access_mask,
        )
        workspace_sources = (
            control_key | query_key | workspace_key | visible_context_key
        )
        answer_sources = workspace_sources | answer_key
        allow = torch.where(workspace_query, workspace_sources, allow)
        allow = torch.where(answer_query, answer_sources, allow)

    allow = torch.where(pad_query, key_segments == SEG_PAD, allow)
    return allow


def _visible_context_key(
    *,
    context_key: torch.Tensor,
    context_access_mask: torch.Tensor | None,
) -> torch.Tensor:
    if context_access_mask is None:
        return torch.zeros_like(context_key)
    if context_access_mask.ndim != 2:
        raise ValueError("context_access_mask must have shape [batch, seq]")
    if context_access_mask.shape != context_key.shape[:1] + context_key.shape[-1:]:
        raise ValueError("context_access_mask must match segment_ids shape")
    access_key = context_access_mask.bool().unsqueeze(1)
    return context_key & access_key
