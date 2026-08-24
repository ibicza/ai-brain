"""Transformer encoder with finite typed heads for language-to-spec parsing."""

from __future__ import annotations

import json
import math
import random
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import torch
from torch import nn
from torch.nn import functional as F

from ai_brain.language_to_spec.generator import load_language_rows
from ai_brain.language_to_spec.schema import (
    PRIMITIVES,
    VARIABLES,
    LanguageProposal,
    ParseStatus,
    SemanticFamily,
    ValidationCode,
    ValidationIssue,
    build_family_specification,
    canonical_specification_json,
    validate_specification,
)
from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.runtime.device import get_device_info

STATUS_LABELS = tuple(ParseStatus)
FAMILY_LABELS = tuple(SemanticFamily)
ERROR_LABELS = (
    ValidationCode.MISSING_DESTINATION,
    ValidationCode.AMBIGUOUS_PRONOUN,
    ValidationCode.UNCLEAR_ORDER,
    ValidationCode.MISSING_PRESERVE_BEHAVIOR,
    ValidationCode.PRESERVE_TRANSFER_CONFLICT,
    ValidationCode.DROP_TRANSFER_CONFLICT,
    ValidationCode.IMPOSSIBLE_TERMINATION,
    ValidationCode.UNSUPPORTED_OPERATION,
)
PHASE_KINDS = ("NONE", "DROP_ONE", "MOVE_ONE")
MAX_PHASES = 3


@dataclass(frozen=True)
class TypedParserConfig:
    max_bytes: int = 512
    d_model: int = 128
    num_layers: int = 2
    num_heads: int = 4
    ffn_dim: int = 512
    dropout: float = 0.1


class TypedLanguageToSpecParser(nn.Module):
    """Finite structured predictor; no AST or mutable state generation."""

    def __init__(self, config: TypedParserConfig | None = None) -> None:
        super().__init__()
        config = config or TypedParserConfig()
        self.config = config
        self.token_embedding = nn.Embedding(258, config.d_model, padding_idx=0)
        self.position_embedding = nn.Embedding(config.max_bytes, config.d_model)
        layer = nn.TransformerEncoderLayer(
            d_model=config.d_model,
            nhead=config.num_heads,
            dim_feedforward=config.ffn_dim,
            dropout=config.dropout,
            batch_first=True,
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(layer, config.num_layers)
        self.final_norm = nn.LayerNorm(config.d_model)
        self.status_head = nn.Linear(config.d_model, len(STATUS_LABELS))
        self.family_head = nn.Linear(config.d_model, len(FAMILY_LABELS))
        self.error_head = nn.Linear(config.d_model, len(ERROR_LABELS))
        self.input_mask_head = nn.Linear(config.d_model, len(VARIABLES))
        self.output_mask_head = nn.Linear(config.d_model, len(VARIABLES))
        self.drop_mask_head = nn.Linear(config.d_model, len(VARIABLES))
        self.preserve_mask_head = nn.Linear(config.d_model, len(VARIABLES))
        self.terminate_mask_head = nn.Linear(config.d_model, len(VARIABLES))
        self.primitive_mask_head = nn.Linear(config.d_model, len(PRIMITIVES))
        self.phase_count_head = nn.Linear(config.d_model, MAX_PHASES + 1)
        self.phase_kind_head = nn.Linear(config.d_model, MAX_PHASES * len(PHASE_KINDS))
        self.phase_source_head = nn.Linear(config.d_model, MAX_PHASES * len(VARIABLES))
        self.phase_destination_head = nn.Linear(
            config.d_model, MAX_PHASES * (len(VARIABLES) + 1)
        )

    def forward(
        self, input_ids: torch.Tensor, attention_mask: torch.Tensor
    ) -> dict[str, torch.Tensor]:
        if input_ids.ndim != 2 or attention_mask.shape != input_ids.shape:
            raise ValueError(
                "input_ids and attention_mask must have shape [batch, seq]"
            )
        batch, length = input_ids.shape
        if length > self.config.max_bytes:
            raise ValueError("input exceeds typed parser max_bytes")
        positions = torch.arange(length, device=input_ids.device).unsqueeze(0)
        hidden = self.token_embedding(input_ids) + self.position_embedding(positions)
        hidden = self.encoder(hidden, src_key_padding_mask=~attention_mask.bool())
        pooled = self.final_norm(hidden[:, 0])
        return {
            "status": self.status_head(pooled),
            "family": self.family_head(pooled),
            "error": self.error_head(pooled),
            "inputs": self.input_mask_head(pooled),
            "outputs": self.output_mask_head(pooled),
            "drops": self.drop_mask_head(pooled),
            "preserve": self.preserve_mask_head(pooled),
            "terminate": self.terminate_mask_head(pooled),
            "primitives": self.primitive_mask_head(pooled),
            "phase_count": self.phase_count_head(pooled),
            "phase_kind": self.phase_kind_head(pooled).view(
                batch, MAX_PHASES, len(PHASE_KINDS)
            ),
            "phase_source": self.phase_source_head(pooled).view(
                batch, MAX_PHASES, len(VARIABLES)
            ),
            "phase_destination": self.phase_destination_head(pooled).view(
                batch, MAX_PHASES, len(VARIABLES) + 1
            ),
        }


def encode_texts(
    texts: Sequence[str], *, max_bytes: int, device: torch.device
) -> tuple[torch.Tensor, torch.Tensor]:
    rows = []
    for text in texts:
        payload = list(text.encode("utf-8"))[: max_bytes - 1]
        rows.append([1, *(value + 2 for value in payload)])
    length = max(len(row) for row in rows)
    ids = torch.zeros((len(rows), length), dtype=torch.long, device=device)
    mask = torch.zeros_like(ids)
    for index, row in enumerate(rows):
        ids[index, : len(row)] = torch.tensor(row, dtype=torch.long, device=device)
        mask[index, : len(row)] = 1
    return ids, mask


def _mask(values: Sequence[str]) -> list[float]:
    selected = set(values)
    return [float(value in selected) for value in VARIABLES]


def _labels(
    rows: Sequence[dict[str, Any]], device: torch.device
) -> dict[str, torch.Tensor]:
    statuses = []
    families = []
    errors = []
    supported = []
    field_masks: dict[str, list[list[float]]] = {
        key: [] for key in ("inputs", "outputs", "drops", "preserve", "terminate")
    }
    primitive_masks = []
    phase_counts = []
    phase_kinds = []
    phase_sources = []
    phase_destinations = []
    for row in rows:
        status = ParseStatus(row["status"])
        statuses.append(STATUS_LABELS.index(status))
        is_supported = status == ParseStatus.SUPPORTED
        supported.append(is_supported)
        family = (
            SemanticFamily(row["semantic_family"])
            if is_supported
            else SemanticFamily.NOOP
        )
        families.append(FAMILY_LABELS.index(family))
        code = (
            ValidationCode(row["error_code"]) if row["error_code"] else ERROR_LABELS[0]
        )
        errors.append(ERROR_LABELS.index(code) if code in ERROR_LABELS else 0)
        spec = (
            ProgramSpecification(**row["canonical_specification"])
            if is_supported
            else ProgramSpecification()
        )
        field_masks["inputs"].append(_mask(spec.inputs))
        field_masks["outputs"].append(_mask(spec.outputs))
        field_masks["drops"].append(_mask(spec.drops))
        field_masks["preserve"].append(_mask(spec.preserve))
        field_masks["terminate"].append(_mask(spec.terminate_when_empty))
        primitive_masks.append(
            [float(value in spec.allowed_primitives) for value in PRIMITIVES]
        )
        phases = list(spec.phase_constraints)
        phase_counts.append(len(phases))
        kinds = []
        sources = []
        destinations = []
        for index in range(MAX_PHASES):
            if index >= len(phases):
                kinds.append(0)
                sources.append(0)
                destinations.append(len(VARIABLES))
                continue
            action, source, destination = phases[index]
            kinds.append(PHASE_KINDS.index(action))
            sources.append(VARIABLES.index(source))
            destinations.append(
                VARIABLES.index(destination)
                if destination is not None
                else len(VARIABLES)
            )
        phase_kinds.append(kinds)
        phase_sources.append(sources)
        phase_destinations.append(destinations)
    result = {
        "status": torch.tensor(statuses, dtype=torch.long, device=device),
        "family": torch.tensor(families, dtype=torch.long, device=device),
        "error": torch.tensor(errors, dtype=torch.long, device=device),
        "supported": torch.tensor(supported, dtype=torch.bool, device=device),
        "primitives": torch.tensor(primitive_masks, dtype=torch.float32, device=device),
        "phase_count": torch.tensor(phase_counts, dtype=torch.long, device=device),
        "phase_kind": torch.tensor(phase_kinds, dtype=torch.long, device=device),
        "phase_source": torch.tensor(phase_sources, dtype=torch.long, device=device),
        "phase_destination": torch.tensor(
            phase_destinations, dtype=torch.long, device=device
        ),
    }
    result.update(
        {
            key: torch.tensor(value, dtype=torch.float32, device=device)
            for key, value in field_masks.items()
        }
    )
    return result


def typed_parser_loss(
    logits: dict[str, torch.Tensor], labels: dict[str, torch.Tensor]
) -> torch.Tensor:
    loss = F.cross_entropy(logits["status"], labels["status"])
    supported = labels["supported"]
    unsupported = ~supported
    if unsupported.any():
        loss = loss + 0.5 * F.cross_entropy(
            logits["error"][unsupported], labels["error"][unsupported]
        )
    if not supported.any():
        return loss
    loss = loss + F.cross_entropy(
        logits["family"][supported], labels["family"][supported]
    )
    loss = loss + 0.5 * F.cross_entropy(
        logits["phase_count"][supported], labels["phase_count"][supported]
    )
    for field in ("inputs", "outputs", "drops", "preserve", "terminate", "primitives"):
        loss = loss + 0.35 * F.binary_cross_entropy_with_logits(
            logits[field][supported], labels[field][supported]
        )
    for phase in range(MAX_PHASES):
        active = supported & (labels["phase_count"] > phase)
        if active.any():
            loss = loss + 0.35 * F.cross_entropy(
                logits["phase_kind"][active, phase], labels["phase_kind"][active, phase]
            )
            loss = loss + 0.35 * F.cross_entropy(
                logits["phase_source"][active, phase],
                labels["phase_source"][active, phase],
            )
            loss = loss + 0.35 * F.cross_entropy(
                logits["phase_destination"][active, phase],
                labels["phase_destination"][active, phase],
            )
    return loss


def _spec_from_logits(
    logits: dict[str, torch.Tensor], index: int
) -> tuple[SemanticFamily, ProgramSpecification]:
    family = FAMILY_LABELS[int(logits["family"][index].argmax().item())]
    source_ids = logits["phase_source"][index].argmax(dim=-1).tolist()
    destination_ids = logits["phase_destination"][index].argmax(dim=-1).tolist()
    if family == SemanticFamily.NOOP:
        sources: tuple[str, ...] = ()
        destination = None
    elif family == SemanticFamily.CLEAR:
        sources = (VARIABLES[source_ids[0]],)
        destination = None
    elif family == SemanticFamily.DRAIN:
        sources = (VARIABLES[source_ids[0]],)
        destination = VARIABLES[destination_ids[0]] if destination_ids[0] < 4 else None
    elif family == SemanticFamily.MERGE_TWO:
        sources = tuple(VARIABLES[value] for value in source_ids[:2])
        destination_id = destination_ids[0]
        destination = VARIABLES[destination_id] if destination_id < 4 else None
    elif family == SemanticFamily.MERGE_THREE:
        sources = tuple(VARIABLES[value] for value in source_ids[:3])
        destination_id = destination_ids[0]
        destination = VARIABLES[destination_id] if destination_id < 4 else None
    else:
        sources = tuple(VARIABLES[value] for value in source_ids[:2])
        destination_id = destination_ids[1]
        destination = VARIABLES[destination_id] if destination_id < 4 else None
    return family, build_family_specification(
        family, sources=sources, destination=destination
    )


@torch.no_grad()
def predict_typed(
    model: TypedLanguageToSpecParser,
    texts: Sequence[str],
    languages: Sequence[str],
    *,
    threshold: float,
    device: torch.device,
) -> list[LanguageProposal]:
    model.eval()
    ids, mask = encode_texts(texts, max_bytes=model.config.max_bytes, device=device)
    logits = model(ids, mask)
    status_probs = logits["status"].softmax(dim=-1)
    family_probs = logits["family"].softmax(dim=-1)
    proposals = []
    for index, text in enumerate(texts):
        status_index = int(status_probs[index].argmax().item())
        status = STATUS_LABELS[status_index]
        confidence = float(status_probs[index, status_index].item())
        if status == ParseStatus.SUPPORTED:
            family_confidence = float(family_probs[index].max().item())
            confidence *= family_confidence
            if confidence < threshold:
                proposals.append(
                    LanguageProposal(
                        ParseStatus.AMBIGUOUS,
                        languages[index],
                        text,
                        issues=(
                            ValidationIssue(
                                ValidationCode.LOW_CONFIDENCE,
                                "confidence",
                                "Structured parser confidence is below the calibrated threshold",
                            ),
                        ),
                        confidence=confidence,
                        parser_name="typed_transformer_v1",
                    )
                )
                continue
            try:
                family, spec = _spec_from_logits(logits, index)
                issues = validate_specification(spec)
            except (ValueError, IndexError) as exc:
                issues = (
                    ValidationIssue(
                        ValidationCode.INVALID_SCHEMA,
                        "specification",
                        str(exc),
                    ),
                )
                family = None
                spec = None
            if issues:
                proposals.append(
                    LanguageProposal(
                        ParseStatus.AMBIGUOUS,
                        languages[index],
                        text,
                        spec,
                        family,
                        issues,
                        confidence,
                        "typed_transformer_v1",
                    )
                )
            else:
                proposals.append(
                    LanguageProposal(
                        status,
                        languages[index],
                        text,
                        spec,
                        family,
                        confidence=confidence,
                        parser_name="typed_transformer_v1",
                    )
                )
        else:
            error_index = int(logits["error"][index].argmax().item())
            code = ERROR_LABELS[error_index]
            proposals.append(
                LanguageProposal(
                    status,
                    languages[index],
                    text,
                    issues=(
                        ValidationIssue(code, "language", "Typed parser abstention"),
                    ),
                    confidence=confidence,
                    parser_name="typed_transformer_v1",
                )
            )
    return proposals


def _semantic_correct(proposal: LanguageProposal, row: dict[str, Any]) -> bool:
    if str(proposal.status) != row["status"]:
        return False
    target = row["canonical_specification"]
    if target is None:
        return bool(
            proposal.issues and str(proposal.issues[0].code) == row["error_code"]
        )
    if proposal.specification is None:
        return False
    return canonical_specification_json(
        proposal.specification
    ) == canonical_specification_json(ProgramSpecification(**target))


def evaluate_typed_rows(
    model: TypedLanguageToSpecParser,
    rows: Sequence[dict[str, Any]],
    *,
    threshold: float,
    device: torch.device,
    batch_size: int = 128,
) -> dict[str, Any]:
    proposals: list[LanguageProposal] = []
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        proposals.extend(
            predict_typed(
                model,
                [row["text"] for row in batch],
                [row["language"] for row in batch],
                threshold=threshold,
                device=device,
            )
        )
    correct = [
        _semantic_correct(proposal, row)
        for proposal, row in zip(proposals, rows, strict=True)
    ]
    accepted = [proposal.status == ParseStatus.SUPPORTED for proposal in proposals]
    supported_target = [row["status"] == str(ParseStatus.SUPPORTED) for row in rows]
    false_accepted = [
        accept and not is_correct
        for accept, is_correct in zip(accepted, correct, strict=True)
    ]
    field_names = (
        "inputs",
        "outputs",
        "transfers",
        "drops",
        "preserve",
        "terminate_when_empty",
        "phase_constraints",
        "allowed_primitives",
    )
    field_scores = {field: [] for field in field_names}
    for proposal, row in zip(proposals, rows, strict=True):
        if row["canonical_specification"] is None or proposal.specification is None:
            continue
        target = ProgramSpecification(**row["canonical_specification"])
        for field in field_names:
            field_scores[field].append(
                float(getattr(proposal.specification, field) == getattr(target, field))
            )
    by_language = {}
    for language in ("ru", "en"):
        indices = [
            index for index, row in enumerate(rows) if row["language"] == language
        ]
        by_language[language] = {
            "count": len(indices),
            "semantic_exact": sum(correct[index] for index in indices)
            / max(1, len(indices)),
            "accepted_precision": sum(
                correct[index] for index in indices if accepted[index]
            )
            / max(1, sum(accepted[index] for index in indices)),
        }
    return {
        "count": len(rows),
        "semantic_specification_exact": sum(correct) / max(1, len(rows)),
        "coverage": sum(accepted) / max(1, len(rows)),
        "accepted_precision": sum(
            c for c, a in zip(correct, accepted, strict=True) if a
        )
        / max(1, sum(accepted)),
        "incorrect_confidently_accepted_rate": sum(false_accepted) / max(1, len(rows)),
        "supported_recall": sum(
            c for c, target in zip(correct, supported_target, strict=True) if target
        )
        / max(1, sum(supported_target)),
        "status_accuracy": sum(
            str(proposal.status) == row["status"]
            for proposal, row in zip(proposals, rows, strict=True)
        )
        / max(1, len(rows)),
        "field_exact": {
            field: sum(scores) / max(1, len(scores))
            for field, scores in field_scores.items()
        },
        "by_language": by_language,
        "rows": [
            {
                "text": row["text"],
                "target_status": row["status"],
                "predicted_status": str(proposal.status),
                "correct": correct[index],
                "confidence": proposal.confidence,
            }
            for index, (proposal, row) in enumerate(zip(proposals, rows, strict=True))
        ],
    }


def calibrate_threshold(
    model: TypedLanguageToSpecParser,
    rows: Sequence[dict[str, Any]],
    *,
    device: torch.device,
) -> tuple[float, list[dict[str, float]]]:
    curve = []
    chosen = 0.99
    for threshold in (0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.93, 0.95, 0.97, 0.99):
        metrics = evaluate_typed_rows(model, rows, threshold=threshold, device=device)
        curve.append(
            {
                "threshold": threshold,
                "coverage": metrics["coverage"],
                "accepted_precision": metrics["accepted_precision"],
                "risk": metrics["incorrect_confidently_accepted_rate"],
            }
        )
        if metrics["incorrect_confidently_accepted_rate"] <= 0.01:
            chosen = threshold
            break
    return chosen, curve


def train_typed_parser(
    *,
    train_path: Path,
    validation_path: Path,
    output_dir: Path,
    seed: int,
    steps: int = 3_000,
    batch_size: int = 64,
    learning_rate: float = 3e-4,
    cpu: bool = False,
    config: TypedParserConfig | None = None,
) -> dict[str, Any]:
    config = config or TypedParserConfig()
    device_info = get_device_info(prefer_cuda=not cpu)
    device = device_info.device
    torch.manual_seed(seed)
    random.seed(seed)
    if device_info.is_cuda:
        torch.cuda.manual_seed_all(seed)
    train_rows = load_language_rows(train_path)
    validation_rows = load_language_rows(validation_path)
    model = TypedLanguageToSpecParser(config).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=learning_rate, weight_decay=0.01
    )
    rng = random.Random(seed)
    history = []
    model.train()
    for step in range(1, steps + 1):
        batch = [train_rows[rng.randrange(len(train_rows))] for _ in range(batch_size)]
        ids, mask = encode_texts(
            [row["text"] for row in batch], max_bytes=config.max_bytes, device=device
        )
        labels = _labels(batch, device)
        logits = model(ids, mask)
        loss = typed_parser_loss(logits, labels)
        if not torch.isfinite(loss):
            raise ValueError(f"Non-finite typed parser loss at step {step}")
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        if step % 250 == 0 or step == steps:
            history.append(
                {
                    "step": step,
                    "train_loss": float(loss.detach().cpu().item()),
                    "grad_norm": float(grad_norm.detach().cpu().item()),
                }
            )
    threshold, risk_curve = calibrate_threshold(model, validation_rows, device=device)
    validation_metrics = evaluate_typed_rows(
        model, validation_rows, threshold=threshold, device=device
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = output_dir / "typed_parser.pt"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "config": asdict(config),
            "seed": seed,
            "steps": steps,
            "threshold": threshold,
            "risk_coverage_curve": risk_curve,
            "validation_metrics": validation_metrics,
            "device": str(device),
            "device_name": device_info.name,
        },
        checkpoint,
    )
    result = {
        "checkpoint": str(checkpoint),
        "seed": seed,
        "steps": steps,
        "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        "threshold": threshold,
        "history": history,
        "risk_coverage_curve": risk_curve,
        "validation_metrics": {
            key: value for key, value in validation_metrics.items() if key != "rows"
        },
        "device": str(device),
        "device_name": device_info.name,
    }
    (output_dir / "train_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return result


def load_typed_parser(
    checkpoint_path: Path, *, device: torch.device
) -> tuple[TypedLanguageToSpecParser, dict[str, Any]]:
    payload = torch.load(checkpoint_path, map_location=device)
    model = TypedLanguageToSpecParser(TypedParserConfig(**payload["config"]))
    model.load_state_dict(payload["model_state_dict"])
    model.to(device).eval()
    return model, payload


def aggregate_seed_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    keys = (
        "semantic_specification_exact",
        "coverage",
        "accepted_precision",
        "incorrect_confidently_accepted_rate",
    )
    result = {}
    for key in keys:
        values = [float(row[key]) for row in rows]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        result[key] = {
            "mean": mean,
            "std": math.sqrt(variance),
            "min": min(values),
            "max": max(values),
        }
    return result
