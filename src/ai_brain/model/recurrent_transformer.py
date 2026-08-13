from __future__ import annotations

import torch
from torch import nn

from ai_brain.model.config import ModelConfig
from ai_brain.model.tiny_transformer import TransformerBlock


class RecurrentCausalTransformer(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()

        config.validate()
        if config.model_type != "recurrent":
            raise ValueError(
                "RecurrentCausalTransformer requires model_type='recurrent'"
            )

        self.config = config

        self.token_embedding = nn.Embedding(config.vocab_size, config.d_model)
        self.position_embedding = nn.Embedding(
            config.max_sequence_length,
            config.d_model,
        )
        self.dropout = nn.Dropout(config.dropout)

        self.input_blocks = nn.ModuleList(
            TransformerBlock(config) for _ in range(config.input_layers)
        )
        self.recurrent_core = TransformerBlock(config)
        self.output_blocks = nn.ModuleList(
            TransformerBlock(config) for _ in range(config.output_layers)
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
        x = self.dropout(x)

        for block in self.input_blocks:
            x = block(x)

        for _ in range(self.config.recurrent_cycles):
            x = self.recurrent_core(x)

        for block in self.output_blocks:
            x = block(x)

        x = self.final_norm(x)
        return self.lm_head(x)
