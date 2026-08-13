from __future__ import annotations

import torch
from torch import nn

from ai_brain.model.config import ModelConfig


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

        self.qkv = nn.Linear(config.d_model, 3 * config.d_model)
        self.output = nn.Linear(config.d_model, config.d_model)
        self.dropout = nn.Dropout(config.dropout)

        causal_mask = torch.tril(
            torch.ones(config.max_sequence_length, config.max_sequence_length)
        )
        self.register_buffer(
            "causal_mask",
            causal_mask.view(
                1, 1, config.max_sequence_length, config.max_sequence_length
            ),
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

        mask = self.causal_mask[:, :, :sequence_length, :sequence_length]
        attention_scores = attention_scores.masked_fill(mask == 0, float("-inf"))

        attention_weights = torch.softmax(attention_scores, dim=-1)
        attention_weights = self.dropout(attention_weights)

        output = attention_weights @ value
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
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()

        config.validate()
        self.config = config

        self.token_embedding = nn.Embedding(config.vocab_size, config.d_model)
        self.position_embedding = nn.Embedding(
            config.max_sequence_length,
            config.d_model,
        )

        self.blocks = nn.ModuleList(
            TransformerBlock(config) for _ in range(config.num_layers)
        )

        self.final_norm = nn.LayerNorm(config.d_model)
        self.lm_head = nn.Linear(config.d_model, config.vocab_size, bias=False)

        if config.tie_embeddings:
            self.lm_head.weight = self.token_embedding.weight

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        if input_ids.ndim != 2:
            raise ValueError("input_ids must have shape [batch_size, sequence_length]")

        _batch_size, sequence_length = input_ids.shape

        if sequence_length > self.config.max_sequence_length:
            raise ValueError(
                "sequence_length exceeds config.max_sequence_length: "
                f"{sequence_length} > {self.config.max_sequence_length}"
            )

        positions = torch.arange(
            sequence_length,
            device=input_ids.device,
            dtype=torch.long,
        )

        x = self.token_embedding(input_ids)
        x = x + self.position_embedding(positions).unsqueeze(0)

        for block in self.blocks:
            x = block(x)

        x = self.final_norm(x)
        return self.lm_head(x)
