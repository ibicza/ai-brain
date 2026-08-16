from __future__ import annotations

from pathlib import Path
from typing import Any

import torch

from ai_brain.language.tokenizer.bpe_tokenizer import (
    ByteLevelBpeTokenizer,
    NumericTokenizationMode,
)
from ai_brain.language.tokenizer.special_tokens import BOS_TOKEN, END_TOKEN, EOS_TOKEN
from ai_brain.language.tokenizer.text_format import format_inference_prompt
from ai_brain.model.factory import build_model, model_config_from_checkpoint
from ai_brain.numeric_features import (
    NUMERIC_FEATURE_KEYS,
    build_numeric_feature_tensors,
)
from ai_brain.numeric_position_features import (
    build_position_feature_tensors,
)
from ai_brain.segments import (
    SEG_ANSWER,
    SegmentAttentionMode,
    build_segment_attention_allow_mask,
)
from ai_brain.training.checkpoint import load_checkpoint


def load_model_for_inference(
    *,
    checkpoint_path: Path,
    tokenizer_path: Path,
    device: torch.device,
) -> tuple[torch.nn.Module, dict[str, Any]]:
    checkpoint = load_checkpoint(checkpoint_path, map_location=device)
    checkpoint_tokenizer_path = checkpoint.get("tokenizer_path")
    if checkpoint_tokenizer_path is not None:
        checkpoint_tokenizer = Path(str(checkpoint_tokenizer_path)).resolve()
        cli_tokenizer = tokenizer_path.resolve()
        if checkpoint_tokenizer != cli_tokenizer:
            raise ValueError(
                "Tokenizer path mismatch: checkpoint has "
                f"{checkpoint_tokenizer_path!r}, CLI provided {str(tokenizer_path)!r}"
            )

    model_config = model_config_from_checkpoint(checkpoint)
    model = build_model(model_config)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()
    return model, checkpoint


def build_inference_input_ids(
    *,
    prompt: str,
    tokenizer: ByteLevelBpeTokenizer,
    device: torch.device,
    numeric_tokenization: NumericTokenizationMode = "default_bpe",
) -> torch.Tensor:
    bos_id = _required_token_id(tokenizer, BOS_TOKEN)
    ids = [
        bos_id,
        *tokenizer.encode(
            format_inference_prompt(prompt),
            numeric_tokenization=numeric_tokenization,
        ),
    ]
    return torch.tensor([ids], dtype=torch.long, device=device)


@torch.no_grad()
def generate_greedy(
    model: torch.nn.Module,
    input_ids: torch.Tensor,
    *,
    max_new_tokens: int,
    eos_token_id: int,
    end_token_id: int,
    tokenizer: ByteLevelBpeTokenizer | None = None,
    numeric_tokenization: NumericTokenizationMode = "default_bpe",
    position_offset: int = 0,
    attention_key_mask: torch.Tensor | None = None,
    segment_ids: torch.Tensor | None = None,
    context_access_mask: torch.Tensor | None = None,
    segment_attention_mode: SegmentAttentionMode = "flat_causal",
) -> list[int]:
    if max_new_tokens <= 0:
        raise ValueError("max_new_tokens must be positive")
    if input_ids.ndim != 2 or input_ids.shape[0] != 1:
        raise ValueError("input_ids must have shape [1, sequence_length]")

    was_training = model.training
    model.eval()
    generated = input_ids
    new_ids: list[int] = []

    for _ in range(max_new_tokens):
        context = generated[:, -model.config.max_sequence_length :]
        context_attention_key_mask = None
        if attention_key_mask is not None:
            generated_count = generated.shape[1] - input_ids.shape[1]
            full_attention_key_mask = attention_key_mask
            if generated_count > 0:
                generated_mask = torch.ones(
                    (1, generated_count),
                    device=attention_key_mask.device,
                    dtype=attention_key_mask.dtype,
                )
                full_attention_key_mask = torch.cat(
                    [attention_key_mask, generated_mask],
                    dim=1,
                )
            context_attention_key_mask = full_attention_key_mask[
                :, -model.config.max_sequence_length :
            ]
        context_attention_allow_mask = None
        if segment_attention_mode != "flat_causal" and segment_ids is not None:
            generated_count = generated.shape[1] - input_ids.shape[1]
            full_segment_ids = segment_ids
            full_context_access_mask = context_access_mask
            if generated_count > 0:
                generated_segments = torch.full(
                    (1, generated_count),
                    SEG_ANSWER,
                    device=segment_ids.device,
                    dtype=segment_ids.dtype,
                )
                full_segment_ids = torch.cat([segment_ids, generated_segments], dim=1)
                if context_access_mask is not None:
                    generated_access = torch.zeros(
                        (1, generated_count),
                        device=context_access_mask.device,
                        dtype=context_access_mask.dtype,
                    )
                    full_context_access_mask = torch.cat(
                        [context_access_mask, generated_access],
                        dim=1,
                    )
            context_segment_ids = full_segment_ids[
                :, -model.config.max_sequence_length :
            ]
            context_access = (
                None
                if full_context_access_mask is None
                else full_context_access_mask[:, -model.config.max_sequence_length :]
            )
            context_attention_allow_mask = build_segment_attention_allow_mask(
                context_segment_ids,
                mode=segment_attention_mode,
                context_access_mask=context_access,
            )
        model_kwargs: dict[str, Any] = {}
        if getattr(model, "supports_position_offset", False):
            model_kwargs["position_offset"] = position_offset
        if getattr(model, "supports_attention_key_mask", False):
            model_kwargs["attention_key_mask"] = context_attention_key_mask
        if getattr(model, "supports_attention_allow_mask", False):
            model_kwargs["attention_allow_mask"] = context_attention_allow_mask
        if getattr(model, "uses_numeric_features", False):
            if tokenizer is None:
                raise ValueError("Numeric model generation requires a tokenizer")
            feature_tensors = _build_context_feature_tensors(
                tokenizer=tokenizer,
                generated=generated,
                numeric_tokenization=numeric_tokenization,
            )
            feature_tensors = {
                key: value[:, -model.config.max_sequence_length :]
                for key, value in feature_tensors.items()
            }
            logits = model(context, **model_kwargs, **feature_tensors)
        elif getattr(model, "uses_abacus_position_features", False):
            if tokenizer is None:
                raise ValueError("Abacus model generation requires a tokenizer")
            feature_tensors = _build_context_position_feature_tensors(
                tokenizer=tokenizer,
                generated=generated,
                numeric_tokenization=numeric_tokenization,
            )
            logits = model(
                context,
                abacus_position_ids=feature_tensors["abacus_position_ids"][
                    :, -model.config.max_sequence_length :
                ],
                **model_kwargs,
            )
        elif getattr(model, "uses_coupled_position_features", False):
            if tokenizer is None:
                raise ValueError("Coupled model generation requires a tokenizer")
            feature_tensors = _build_context_position_feature_tensors(
                tokenizer=tokenizer,
                generated=generated,
                numeric_tokenization=numeric_tokenization,
            )
            logits = model(
                context,
                coupled_position_ids=feature_tensors["coupled_position_ids"][
                    :, -model.config.max_sequence_length :
                ],
                **model_kwargs,
            )
        elif getattr(model, "uses_gated_place_features", False):
            if tokenizer is None:
                raise ValueError("Gated-place model generation requires a tokenizer")
            feature_tensors = _build_context_feature_tensors(
                tokenizer=tokenizer,
                generated=generated,
                numeric_tokenization=numeric_tokenization,
            )
            logits = model(
                context,
                digit_place_ids=feature_tensors["digit_place_ids"][
                    :, -model.config.max_sequence_length :
                ],
                **model_kwargs,
            )
        else:
            logits = model(context, **model_kwargs)
        next_token_id = int(torch.argmax(logits[:, -1, :], dim=-1).item())
        next_token = torch.tensor(
            [[next_token_id]], device=generated.device, dtype=torch.long
        )
        generated = torch.cat([generated, next_token], dim=1)
        new_ids.append(next_token_id)
        if next_token_id in {eos_token_id, end_token_id}:
            break

    if was_training:
        model.train()
    return new_ids


def generate_answer_ids(
    *,
    model: torch.nn.Module,
    tokenizer: ByteLevelBpeTokenizer,
    prompt: str,
    max_new_tokens: int,
    device: torch.device,
    numeric_tokenization: NumericTokenizationMode = "default_bpe",
    position_offset: int = 0,
    attention_key_mask: torch.Tensor | None = None,
    segment_ids: torch.Tensor | None = None,
    context_access_mask: torch.Tensor | None = None,
    segment_attention_mode: SegmentAttentionMode = "flat_causal",
) -> list[int]:
    input_ids = build_inference_input_ids(
        prompt=prompt,
        tokenizer=tokenizer,
        device=device,
        numeric_tokenization=numeric_tokenization,
    )
    return generate_greedy(
        model,
        input_ids,
        max_new_tokens=max_new_tokens,
        eos_token_id=_required_token_id(tokenizer, EOS_TOKEN),
        end_token_id=_required_token_id(tokenizer, END_TOKEN),
        tokenizer=tokenizer,
        numeric_tokenization=numeric_tokenization,
        position_offset=position_offset,
        attention_key_mask=attention_key_mask,
        segment_ids=segment_ids,
        context_access_mask=context_access_mask,
        segment_attention_mode=segment_attention_mode,
    )


def _build_context_feature_tensors(
    *,
    tokenizer: ByteLevelBpeTokenizer,
    generated: torch.Tensor,
    numeric_tokenization: NumericTokenizationMode,
) -> dict[str, torch.Tensor]:
    input_ids = generated[0].detach().cpu().tolist()
    text_without_bos = tokenizer.decode(input_ids[1:], skip_special_tokens=False)
    features = build_numeric_feature_tensors(
        input_ids=input_ids,
        text_without_bos=text_without_bos,
        tokenizer=tokenizer,
        numeric_tokenization=numeric_tokenization,
        device=generated.device,
    )
    return {key: features[key] for key in NUMERIC_FEATURE_KEYS}


def _build_context_position_feature_tensors(
    *,
    tokenizer: ByteLevelBpeTokenizer,
    generated: torch.Tensor,
    numeric_tokenization: NumericTokenizationMode,
) -> dict[str, torch.Tensor]:
    input_ids = generated[0].detach().cpu().tolist()
    text_without_bos = tokenizer.decode(input_ids[1:], skip_special_tokens=False)
    return build_position_feature_tensors(
        input_ids=input_ids,
        text_without_bos=text_without_bos,
        tokenizer=tokenizer,
        numeric_tokenization=numeric_tokenization,
        device=generated.device,
    )


def _required_token_id(tokenizer: ByteLevelBpeTokenizer, token: str) -> int:
    token_id = tokenizer.token_to_id(token)
    if token_id is None:
        raise ValueError(f"Tokenizer is missing required special token: {token}")
    return token_id
