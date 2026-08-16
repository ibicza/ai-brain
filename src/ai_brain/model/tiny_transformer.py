from __future__ import annotations

import torch
from torch import nn

from ai_brain.model.config import ModelConfig
from ai_brain.numeric_features import (
    DIGIT_PLACE_VOCAB_SIZE,
    DIGIT_VALUE_VOCAB_SIZE,
    FEATURE_NONE_ID,
    NUMBER_ROLE_VOCAB_SIZE,
    OPERATION_STEP_VOCAB_SIZE,
)
from ai_brain.numeric_position_features import POSITION_FEATURE_VOCAB_SIZE


class FeedForward(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()

        self.net = nn.Sequential(
            nn.Linear(config.d_model, config.ffn_hidden_dim),
            nn.GELU(),
            nn.Linear(config.ffn_hidden_dim, config.d_model),
            nn.Dropout(config.dropout),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class CausalSelfAttention(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()

        if config.d_model % config.num_heads != 0:
            raise ValueError("d_model must be divisible by num_heads")

        self.num_heads = config.num_heads
        self.head_dim = config.d_model // config.num_heads
        self.position_encoding = config.position_encoding
        self.max_relative_position = config.max_sequence_length - 1

        self.qkv = nn.Linear(config.d_model, 3 * config.d_model)
        self.output = nn.Linear(config.d_model, config.d_model)
        self.dropout = nn.Dropout(config.dropout)
        if config.position_encoding == "relative":
            relative_vocab_size = 2 * self.max_relative_position + 1
            self.relative_key_embedding = nn.Embedding(
                relative_vocab_size,
                self.head_dim,
            )
            self.relative_value_embedding = nn.Embedding(
                relative_vocab_size,
                self.head_dim,
            )
        else:
            self.relative_key_embedding = None
            self.relative_value_embedding = None

        causal_mask = torch.tril(
            torch.ones(config.max_sequence_length, config.max_sequence_length)
        )
        indices = torch.arange(config.max_sequence_length)
        relative_position_ids = (indices.view(1, -1) - indices.view(-1, 1)).clamp(
            min=-self.max_relative_position,
            max=self.max_relative_position,
        )
        relative_position_ids = relative_position_ids + self.max_relative_position
        self.register_buffer(
            "causal_mask",
            causal_mask.view(
                1, 1, config.max_sequence_length, config.max_sequence_length
            ),
            persistent=False,
        )
        self.register_buffer(
            "relative_position_ids",
            relative_position_ids,
            persistent=False,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch_size, sequence_length, d_model = x.shape

        qkv = self.qkv(x)
        query, key, value = qkv.chunk(3, dim=-1)

        query = query.view(
            batch_size, sequence_length, self.num_heads, self.head_dim
        ).transpose(1, 2)
        key = key.view(
            batch_size, sequence_length, self.num_heads, self.head_dim
        ).transpose(1, 2)
        value = value.view(
            batch_size, sequence_length, self.num_heads, self.head_dim
        ).transpose(1, 2)

        attention_scores = query @ key.transpose(-2, -1)
        attention_scores = attention_scores / self.head_dim**0.5
        if self.relative_key_embedding is not None:
            relative_ids = self.relative_position_ids[
                :sequence_length,
                :sequence_length,
            ]
            relative_keys = self.relative_key_embedding(relative_ids)
            relative_scores = torch.einsum("bhid,ijd->bhij", query, relative_keys)
            attention_scores = attention_scores + relative_scores / self.head_dim**0.5

        mask = self.causal_mask[:, :, :sequence_length, :sequence_length]
        attention_scores = attention_scores.masked_fill(mask == 0, float("-inf"))

        attention_weights = torch.softmax(attention_scores, dim=-1)
        attention_weights = self.dropout(attention_weights)

        output = attention_weights @ value
        if self.relative_value_embedding is not None:
            relative_ids = self.relative_position_ids[
                :sequence_length,
                :sequence_length,
            ]
            relative_values = self.relative_value_embedding(relative_ids)
            output = output + torch.einsum(
                "bhij,ijd->bhid",
                attention_weights,
                relative_values,
            )
        output = (
            output.transpose(1, 2)
            .contiguous()
            .view(batch_size, sequence_length, d_model)
        )

        return self.output(output)


class TransformerBlock(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()

        self.attention_norm = nn.LayerNorm(config.d_model)
        self.attention = CausalSelfAttention(config)
        self.ffn_norm = nn.LayerNorm(config.d_model)
        self.ffn = FeedForward(config)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.attention(self.attention_norm(x))
        x = x + self.ffn(self.ffn_norm(x))
        return x


class TinyCausalTransformer(nn.Module):
    supports_position_offset = True

    def __init__(self, config: ModelConfig) -> None:
        super().__init__()

        config.validate()
        if config.model_type != "tiny":
            raise ValueError("TinyCausalTransformer requires model_type='tiny'")
        self.config = config

        self.token_embedding = nn.Embedding(config.vocab_size, config.d_model)
        self.position_embedding = (
            nn.Embedding(
                config.max_sequence_length,
                config.d_model,
            )
            if config.position_encoding == "absolute"
            else None
        )

        self.blocks = nn.ModuleList(
            TransformerBlock(config) for _ in range(config.num_layers)
        )

        self.final_norm = nn.LayerNorm(config.d_model)
        self.lm_head = nn.Linear(config.d_model, config.vocab_size, bias=False)

        if config.tie_embeddings:
            self.lm_head.weight = self.token_embedding.weight

    def forward(
        self,
        input_ids: torch.Tensor,
        *,
        position_offset: int | torch.Tensor = 0,
    ) -> torch.Tensor:
        x = self.embed_tokens_and_positions(
            input_ids,
            position_offset=position_offset,
        )
        return self.forward_embeddings(x)

    def embed_tokens_and_positions(
        self,
        input_ids: torch.Tensor,
        *,
        position_offset: int | torch.Tensor = 0,
    ) -> torch.Tensor:
        if input_ids.ndim != 2:
            raise ValueError("input_ids must have shape [batch_size, sequence_length]")

        batch_size, sequence_length = input_ids.shape

        if sequence_length > self.config.max_sequence_length:
            raise ValueError(
                "sequence_length exceeds config.max_sequence_length: "
                f"{sequence_length} > {self.config.max_sequence_length}"
            )

        x = self.token_embedding(input_ids)
        if self.position_embedding is None:
            return x

        positions = torch.arange(
            sequence_length,
            device=input_ids.device,
            dtype=torch.long,
        )
        if isinstance(position_offset, torch.Tensor):
            if position_offset.ndim == 0:
                positions = positions + position_offset.to(
                    device=input_ids.device,
                    dtype=torch.long,
                )
            elif position_offset.ndim == 1:
                if position_offset.shape != (batch_size,):
                    raise ValueError(
                        "position_offset tensor must be scalar, shape [batch_size], "
                        "or exact shape [batch_size, sequence_length]"
                    )
                offsets = position_offset.to(device=input_ids.device, dtype=torch.long)
                positions = positions.unsqueeze(0) + offsets.unsqueeze(1)
            else:
                if position_offset.shape != (batch_size, sequence_length):
                    raise ValueError(
                        "position_offset tensor must be scalar, shape [batch_size], "
                        "or exact shape [batch_size, sequence_length]"
                    )
                positions = position_offset.to(
                    device=input_ids.device, dtype=torch.long
                )
        else:
            positions = positions + int(position_offset)

        max_position = int(positions.max().detach().cpu().item())
        min_position = int(positions.min().detach().cpu().item())
        if min_position < 0:
            raise ValueError(
                f"position offset produces negative position: {min_position}"
            )
        if max_position >= self.config.max_sequence_length:
            raise ValueError(
                "position offset exceeds config.max_sequence_length: "
                f"{max_position} >= {self.config.max_sequence_length}"
            )
        position_embeddings = self.position_embedding(positions)
        if position_embeddings.ndim == 2:
            position_embeddings = position_embeddings.unsqueeze(0)

        return x + position_embeddings

    def forward_embeddings(self, x: torch.Tensor) -> torch.Tensor:
        for block in self.blocks:
            x = block(x)

        x = self.final_norm(x)
        return self.lm_head(x)


class TinyNumericCausalTransformer(TinyCausalTransformer):
    uses_numeric_features = True

    def __init__(self, config: ModelConfig) -> None:
        numeric_config = ModelConfig(**{**config.__dict__, "model_type": "tiny"})
        super().__init__(numeric_config)
        if config.model_type != "numeric":
            raise ValueError(
                "TinyNumericCausalTransformer requires model_type='numeric'"
            )
        self.config = config
        self.digit_value_embedding = nn.Embedding(
            DIGIT_VALUE_VOCAB_SIZE,
            config.d_model,
            padding_idx=FEATURE_NONE_ID,
        )
        self.digit_place_embedding = nn.Embedding(
            DIGIT_PLACE_VOCAB_SIZE,
            config.d_model,
            padding_idx=FEATURE_NONE_ID,
        )
        self.number_role_embedding = nn.Embedding(
            NUMBER_ROLE_VOCAB_SIZE,
            config.d_model,
            padding_idx=FEATURE_NONE_ID,
        )
        self.operation_step_embedding = nn.Embedding(
            OPERATION_STEP_VOCAB_SIZE,
            config.d_model,
            padding_idx=FEATURE_NONE_ID,
        )

    def forward(
        self,
        input_ids: torch.Tensor,
        *,
        digit_value_ids: torch.Tensor | None = None,
        digit_place_ids: torch.Tensor | None = None,
        number_role_ids: torch.Tensor | None = None,
        operation_step_ids: torch.Tensor | None = None,
        position_offset: int | torch.Tensor = 0,
    ) -> torch.Tensor:
        x = self.embed_tokens_and_positions(
            input_ids,
            position_offset=position_offset,
        )
        x = x + self.digit_value_embedding(
            _feature_ids_or_none(digit_value_ids, input_ids)
        )
        x = x + self.digit_place_embedding(
            _feature_ids_or_none(digit_place_ids, input_ids)
        )
        x = x + self.number_role_embedding(
            _feature_ids_or_none(number_role_ids, input_ids)
        )
        x = x + self.operation_step_embedding(
            _feature_ids_or_none(operation_step_ids, input_ids)
        )
        return self.forward_embeddings(x)


class TinyAbacusPositionTransformer(TinyCausalTransformer):
    uses_abacus_position_features = True

    def __init__(self, config: ModelConfig) -> None:
        tiny_config = ModelConfig(**{**config.__dict__, "model_type": "tiny"})
        super().__init__(tiny_config)
        if config.model_type != "abacus":
            raise ValueError(
                "TinyAbacusPositionTransformer requires model_type='abacus'"
            )
        self.config = config
        self.abacus_position_embedding = nn.Embedding(
            POSITION_FEATURE_VOCAB_SIZE,
            config.d_model,
            padding_idx=FEATURE_NONE_ID,
        )

    def forward(
        self,
        input_ids: torch.Tensor,
        *,
        abacus_position_ids: torch.Tensor | None = None,
        position_offset: int | torch.Tensor = 0,
    ) -> torch.Tensor:
        x = self.embed_tokens_and_positions(
            input_ids,
            position_offset=position_offset,
        )
        x = x + self.abacus_position_embedding(
            _feature_ids_or_none(abacus_position_ids, input_ids)
        )
        return self.forward_embeddings(x)


class TinyCoupledPositionTransformer(TinyCausalTransformer):
    uses_coupled_position_features = True

    def __init__(self, config: ModelConfig) -> None:
        tiny_config = ModelConfig(**{**config.__dict__, "model_type": "tiny"})
        super().__init__(tiny_config)
        if config.model_type != "coupled":
            raise ValueError(
                "TinyCoupledPositionTransformer requires model_type='coupled'"
            )
        self.config = config
        self.coupled_position_embedding = nn.Embedding(
            POSITION_FEATURE_VOCAB_SIZE,
            config.d_model,
            padding_idx=FEATURE_NONE_ID,
        )

    def forward(
        self,
        input_ids: torch.Tensor,
        *,
        coupled_position_ids: torch.Tensor | None = None,
        position_offset: int | torch.Tensor = 0,
    ) -> torch.Tensor:
        x = self.embed_tokens_and_positions(
            input_ids,
            position_offset=position_offset,
        )
        x = x + self.coupled_position_embedding(
            _feature_ids_or_none(coupled_position_ids, input_ids)
        )
        return self.forward_embeddings(x)


class TinyGatedPlaceTransformer(TinyCausalTransformer):
    uses_gated_place_features = True

    def __init__(self, config: ModelConfig) -> None:
        tiny_config = ModelConfig(**{**config.__dict__, "model_type": "tiny"})
        super().__init__(tiny_config)
        if config.model_type != "gated_place":
            raise ValueError(
                "TinyGatedPlaceTransformer requires model_type='gated_place'"
            )
        self.config = config
        self.digit_place_embedding = nn.Embedding(
            DIGIT_PLACE_VOCAB_SIZE,
            config.d_model,
            padding_idx=FEATURE_NONE_ID,
        )
        self.place_alpha = nn.Parameter(torch.tensor(0.0))

    def forward(
        self,
        input_ids: torch.Tensor,
        *,
        digit_place_ids: torch.Tensor | None = None,
        position_offset: int | torch.Tensor = 0,
    ) -> torch.Tensor:
        x = self.embed_tokens_and_positions(
            input_ids,
            position_offset=position_offset,
        )
        x = x + self.place_alpha * self.digit_place_embedding(
            _feature_ids_or_none(digit_place_ids, input_ids)
        )
        return self.forward_embeddings(x)


def _feature_ids_or_none(
    feature_ids: torch.Tensor | None,
    input_ids: torch.Tensor,
) -> torch.Tensor:
    if feature_ids is None:
        return torch.zeros_like(input_ids, dtype=torch.long)
    if feature_ids.shape != input_ids.shape:
        raise ValueError("numeric feature ids must match input_ids shape")
    return feature_ids.long()
