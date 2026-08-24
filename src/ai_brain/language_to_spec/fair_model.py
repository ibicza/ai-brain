"""Compute-matched catalog and factorized parsers for the M-23.1 fair retest."""

from __future__ import annotations

import copy
import json
import math
import random
import re
import time
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import mean
from typing import Any, Literal

import torch
from torch import nn
from torch.nn import functional as F

from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.language.tokenizer.special_tokens import BOS_TOKEN
from ai_brain.language_to_spec.equivalence import (
    semantic_specification_equal,
    structural_specification_equal,
)
from ai_brain.language_to_spec.fair_data import (
    assignments_for,
    roles_from_assignment,
)
from ai_brain.language_to_spec.generator import load_language_rows
from ai_brain.language_to_spec.json_control import valid_control_answers
from ai_brain.language_to_spec.schema import (
    VARIABLES,
    LanguageProposal,
    ParseStatus,
    SemanticFamily,
    ValidationCode,
    ValidationIssue,
    build_family_specification,
    canonicalize_specification,
    strict_specification_from_json,
    validate_specification,
)
from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.runtime.device import get_device_info

EncodingMode = Literal["byte", "bpe"]
CandidateKind = Literal["catalog", "factorized"]
ConfidenceMethod = Literal["product", "minimum", "temperature_joint"]

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
MAX_SOURCES = 3
DESTINATION_NONE = len(VARIABLES)
ORDER_LABELS = ("DROP_THEN_TRANSFER", "TRANSFER_THEN_DROP")


class InputTooLongError(ValueError):
    pass


@dataclass(frozen=True)
class FairParserConfig:
    candidate_kind: CandidateKind
    encoding: EncodingMode
    vocab_size: int
    max_length: int
    tokenizer_path: str | None = None
    d_model: int = 128
    num_layers: int = 2
    num_heads: int = 4
    ffn_dim: int = 512
    dropout: float = 0.1


@dataclass(frozen=True)
class CalibrationResult:
    status: str
    method: ConfidenceMethod
    threshold: float | None
    temperature: float
    coverage: float
    accepted_precision: float
    accepted_count: int
    curve: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class StructuredPrediction:
    proposal: LanguageProposal
    confidence_scores: dict[str, float]
    raw_supported: bool
    invalid_reason: str | None = None


def _tokenizer(config: FairParserConfig) -> ByteLevelBpeTokenizer | None:
    if config.encoding == "byte":
        return None
    if not config.tokenizer_path:
        raise ValueError("BPE parser requires tokenizer_path")
    return ByteLevelBpeTokenizer.load(Path(config.tokenizer_path))


def encoded_length(
    text: str,
    config: FairParserConfig,
    tokenizer: ByteLevelBpeTokenizer | None = None,
) -> int:
    if config.encoding == "byte":
        return len(text.encode("utf-8")) + 1
    tokenizer = tokenizer or _tokenizer(config)
    assert tokenizer is not None
    return len(tokenizer.encode(text)) + 1


def encode_texts_v2(
    texts: Sequence[str],
    *,
    config: FairParserConfig,
    device: torch.device,
    tokenizer: ByteLevelBpeTokenizer | None = None,
) -> tuple[torch.Tensor, torch.Tensor, list[int]]:
    tokenizer = tokenizer or _tokenizer(config)
    rows: list[list[int]] = []
    lengths: list[int] = []
    for index, text in enumerate(texts):
        if config.encoding == "byte":
            row = [1, *(value + 2 for value in text.encode("utf-8"))]
        else:
            assert tokenizer is not None
            bos_id = tokenizer.token_to_id(BOS_TOKEN)
            if bos_id is None:
                raise ValueError("BPE tokenizer is missing BOS")
            row = [bos_id, *tokenizer.encode(text)]
        lengths.append(len(row))
        if len(row) > config.max_length:
            raise InputTooLongError(
                f"Input {index} needs {len(row)} {config.encoding} tokens; "
                f"configured maximum is {config.max_length}"
            )
        rows.append(row)
    width = max((len(row) for row in rows), default=1)
    ids = torch.zeros((len(rows), width), dtype=torch.long, device=device)
    mask = torch.zeros_like(ids)
    for index, row in enumerate(rows):
        ids[index, : len(row)] = torch.tensor(row, dtype=torch.long, device=device)
        mask[index, : len(row)] = 1
    return ids, mask, lengths


def input_length_statistics(
    rows: Sequence[dict[str, Any]], config: FairParserConfig
) -> dict[str, Any]:
    tokenizer = _tokenizer(config)
    lengths = [encoded_length(row["text"], config, tokenizer) for row in rows]
    ordered = sorted(lengths)
    p95 = ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)] if ordered else 0
    by_language = {}
    for language in ("ru", "en"):
        selected = [
            length
            for length, row in zip(lengths, rows, strict=True)
            if row["language"] == language
        ]
        by_language[language] = {
            "count": len(selected),
            "avg": mean(selected) if selected else 0.0,
            "max": max(selected, default=0),
            "truncated": sum(length > config.max_length for length in selected),
        }
    return {
        "count": len(lengths),
        "average": mean(lengths) if lengths else 0.0,
        "p95": p95,
        "maximum": max(lengths, default=0),
        "max_length": config.max_length,
        "truncated": sum(length > config.max_length for length in lengths),
        "by_language": by_language,
    }


class FairTextEncoder(nn.Module):
    def __init__(self, config: FairParserConfig) -> None:
        super().__init__()
        self.config = config
        self.token_embedding = nn.Embedding(
            config.vocab_size, config.d_model, padding_idx=0
        )
        self.position_embedding = nn.Embedding(config.max_length, config.d_model)
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

    def forward(
        self, input_ids: torch.Tensor, attention_mask: torch.Tensor
    ) -> torch.Tensor:
        if input_ids.shape != attention_mask.shape or input_ids.ndim != 2:
            raise ValueError("input_ids and attention_mask must be [batch, sequence]")
        if input_ids.shape[1] > self.config.max_length:
            raise InputTooLongError("Encoded input exceeds configured model length")
        positions = torch.arange(input_ids.shape[1], device=input_ids.device)[None, :]
        hidden = self.token_embedding(input_ids) + self.position_embedding(positions)
        hidden = self.encoder(hidden, src_key_padding_mask=~attention_mask.bool())
        return self.final_norm(hidden[:, 0])


class CatalogSpecificationClassifier(nn.Module):
    def __init__(self, config: FairParserConfig, catalog_size: int) -> None:
        super().__init__()
        self.config = config
        self.encoder = FairTextEncoder(config)
        self.catalog_head = nn.Linear(config.d_model, catalog_size)

    def forward(
        self, input_ids: torch.Tensor, attention_mask: torch.Tensor
    ) -> dict[str, torch.Tensor]:
        return {"catalog": self.catalog_head(self.encoder(input_ids, attention_mask))}


class FactorizedLanguageToSpecParserV2(nn.Module):
    """Every output head participates in proposal construction or rejection."""

    def __init__(self, config: FairParserConfig) -> None:
        super().__init__()
        self.config = config
        self.encoder = FairTextEncoder(config)
        width = config.d_model
        self.status_head = nn.Linear(width, len(STATUS_LABELS))
        self.error_head = nn.Linear(width, len(ERROR_LABELS))
        self.family_head = nn.Linear(width, len(FAMILY_LABELS))
        self.source_count_head = nn.Linear(width, MAX_SOURCES + 1)
        self.source_slots_head = nn.Linear(width, MAX_SOURCES * len(VARIABLES))
        self.destination_head = nn.Linear(width, len(VARIABLES) + 1)
        self.preserve_head = nn.Linear(width, len(VARIABLES))
        self.termination_head = nn.Linear(width, len(VARIABLES))
        self.order_head = nn.Linear(width, len(ORDER_LABELS))

    def forward(
        self, input_ids: torch.Tensor, attention_mask: torch.Tensor
    ) -> dict[str, torch.Tensor]:
        pooled = self.encoder(input_ids, attention_mask)
        batch = pooled.shape[0]
        return {
            "status": self.status_head(pooled),
            "error": self.error_head(pooled),
            "family": self.family_head(pooled),
            "source_count": self.source_count_head(pooled),
            "source_slots": self.source_slots_head(pooled).view(
                batch, MAX_SOURCES, len(VARIABLES)
            ),
            "destination": self.destination_head(pooled),
            "preserve": self.preserve_head(pooled),
            "termination": self.termination_head(pooled),
            "order": self.order_head(pooled),
        }


def catalog_answers() -> tuple[str, ...]:
    return valid_control_answers()


def _catalog_label(row: dict[str, Any], catalog: tuple[str, ...]) -> int:
    try:
        return catalog.index(row["answer"])
    except ValueError as exc:
        raise ValueError("Row answer is outside the finite Stage-1 catalog") from exc


def _required_source_count(family: SemanticFamily) -> int:
    return {
        SemanticFamily.NOOP: 0,
        SemanticFamily.CLEAR: 1,
        SemanticFamily.DRAIN: 1,
        SemanticFamily.MERGE_TWO: 2,
        SemanticFamily.MERGE_THREE: 3,
        SemanticFamily.DROP_THEN_TRANSFER: 2,
    }[family]


def _factorized_labels(
    rows: Sequence[dict[str, Any]], device: torch.device
) -> dict[str, torch.Tensor]:
    values: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        status = ParseStatus(row["status"])
        values["status"].append(STATUS_LABELS.index(status))
        supported = status == ParseStatus.SUPPORTED
        values["supported"].append(supported)
        code = (
            ValidationCode(row["error_code"]) if row["error_code"] else ERROR_LABELS[0]
        )
        values["error"].append(ERROR_LABELS.index(code))
        if supported:
            family = SemanticFamily(row["semantic_family"])
            spec = ProgramSpecification(**row["canonical_specification"])
            assignment = tuple(row["metadata"]["assignment"])
            sources, destination = roles_from_assignment(family, assignment)
        else:
            family = SemanticFamily.NOOP
            spec = ProgramSpecification()
            sources = ()
            destination = None
        values["family"].append(FAMILY_LABELS.index(family))
        values["source_count"].append(len(sources))
        padded_sources = [VARIABLES.index(source) for source in sources]
        padded_sources.extend([0] * (MAX_SOURCES - len(padded_sources)))
        values["source_slots"].append(padded_sources)
        values["destination"].append(
            VARIABLES.index(destination)
            if destination is not None
            else DESTINATION_NONE
        )
        values["preserve"].append(
            [float(variable in spec.preserve) for variable in VARIABLES]
        )
        values["termination"].append(
            [float(variable in spec.terminate_when_empty) for variable in VARIABLES]
        )
        values["order"].append(0)
        values["order_sensitive"].append(
            family == SemanticFamily.DROP_THEN_TRANSFER and supported
        )
    return {
        "status": torch.tensor(values["status"], dtype=torch.long, device=device),
        "supported": torch.tensor(values["supported"], dtype=torch.bool, device=device),
        "error": torch.tensor(values["error"], dtype=torch.long, device=device),
        "family": torch.tensor(values["family"], dtype=torch.long, device=device),
        "source_count": torch.tensor(
            values["source_count"], dtype=torch.long, device=device
        ),
        "source_slots": torch.tensor(
            values["source_slots"], dtype=torch.long, device=device
        ),
        "destination": torch.tensor(
            values["destination"], dtype=torch.long, device=device
        ),
        "preserve": torch.tensor(
            values["preserve"], dtype=torch.float32, device=device
        ),
        "termination": torch.tensor(
            values["termination"], dtype=torch.float32, device=device
        ),
        "order": torch.tensor(values["order"], dtype=torch.long, device=device),
        "order_sensitive": torch.tensor(
            values["order_sensitive"], dtype=torch.bool, device=device
        ),
    }


def factorized_loss(
    logits: dict[str, torch.Tensor], labels: dict[str, torch.Tensor]
) -> torch.Tensor:
    loss = F.cross_entropy(logits["status"], labels["status"])
    supported = labels["supported"]
    if (~supported).any():
        loss = loss + F.cross_entropy(
            logits["error"][~supported], labels["error"][~supported]
        )
    if not supported.any():
        return loss
    loss = loss + F.cross_entropy(
        logits["family"][supported], labels["family"][supported]
    )
    loss = loss + F.cross_entropy(
        logits["source_count"][supported], labels["source_count"][supported]
    )
    for slot in range(MAX_SOURCES):
        active = supported & (labels["source_count"] > slot)
        if active.any():
            loss = loss + F.cross_entropy(
                logits["source_slots"][active, slot],
                labels["source_slots"][active, slot],
            )
    loss = loss + F.cross_entropy(
        logits["destination"][supported], labels["destination"][supported]
    )
    loss = loss + F.binary_cross_entropy_with_logits(
        logits["preserve"][supported], labels["preserve"][supported]
    )
    loss = loss + F.binary_cross_entropy_with_logits(
        logits["termination"][supported], labels["termination"][supported]
    )
    if labels["order_sensitive"].any():
        active = labels["order_sensitive"]
        loss = loss + F.cross_entropy(logits["order"][active], labels["order"][active])
    return loss


def _confidence_scores(
    probabilities: list[float], temperature: float = 1.0
) -> dict[str, float]:
    clipped = [min(1.0 - 1e-7, max(1e-7, probability)) for probability in probabilities]
    product = math.prod(clipped)
    minimum = min(clipped)
    logit = math.log(product / (1.0 - product))
    temperature_joint = 1.0 / (1.0 + math.exp(-logit / temperature))
    return {
        "product": product,
        "minimum": minimum,
        "temperature_joint": temperature_joint,
    }


def _proposal_from_catalog_answer(
    answer: str, *, text: str, language: str, confidence: float
) -> LanguageProposal:
    payload = json.loads(answer)
    status = ParseStatus(payload["status"])
    if status == ParseStatus.SUPPORTED:
        specification = strict_specification_from_json(payload["specification"])
        family = infer_semantic_family(specification)
        return LanguageProposal(
            status,
            language,
            text,
            specification,
            family,
            confidence=confidence,
            parser_name="finite_catalog_classifier",
        )
    code = ValidationCode(payload["error"])
    return LanguageProposal(
        status,
        language,
        text,
        issues=(ValidationIssue(code, "language", "Finite catalog decision"),),
        confidence=confidence,
        parser_name="finite_catalog_classifier",
    )


def infer_semantic_family(spec: ProgramSpecification) -> SemanticFamily:
    if not spec.phase_constraints:
        return SemanticFamily.NOOP
    if spec.drops and not spec.transfers:
        return SemanticFamily.CLEAR
    if spec.drops and spec.transfers:
        return SemanticFamily.DROP_THEN_TRANSFER
    return {
        1: SemanticFamily.DRAIN,
        2: SemanticFamily.MERGE_TWO,
        3: SemanticFamily.MERGE_THREE,
    }[len(spec.transfers)]


def _decode_catalog(
    logits: dict[str, torch.Tensor],
    texts: Sequence[str],
    languages: Sequence[str],
    catalog: tuple[str, ...],
) -> list[StructuredPrediction]:
    probabilities = logits["catalog"].softmax(dim=-1)
    output = []
    for index, text in enumerate(texts):
        class_index = int(probabilities[index].argmax().item())
        confidence = float(probabilities[index, class_index].item())
        proposal = _proposal_from_catalog_answer(
            catalog[class_index],
            text=text,
            language=languages[index],
            confidence=confidence,
        )
        output.append(
            StructuredPrediction(
                proposal,
                _confidence_scores([confidence]),
                proposal.status == ParseStatus.SUPPORTED,
            )
        )
    return output


def _predicted_binary_confidence(logit: torch.Tensor) -> tuple[bool, float]:
    probability = float(logit.sigmoid().item())
    return probability >= 0.5, max(probability, 1.0 - probability)


def _invalid_proposal(
    text: str,
    language: str,
    confidence: float,
    message: str,
    *,
    parser_name: str,
) -> LanguageProposal:
    return LanguageProposal(
        ParseStatus.AMBIGUOUS,
        language,
        text,
        issues=(
            ValidationIssue(ValidationCode.INVALID_SCHEMA, "specification", message),
        ),
        confidence=confidence,
        parser_name=parser_name,
    )


def _decode_factorized(
    logits: dict[str, torch.Tensor],
    texts: Sequence[str],
    languages: Sequence[str],
) -> list[StructuredPrediction]:
    status_probs = logits["status"].softmax(dim=-1)
    error_probs = logits["error"].softmax(dim=-1)
    family_probs = logits["family"].softmax(dim=-1)
    count_probs = logits["source_count"].softmax(dim=-1)
    source_probs = logits["source_slots"].softmax(dim=-1)
    destination_probs = logits["destination"].softmax(dim=-1)
    order_probs = logits["order"].softmax(dim=-1)
    predictions = []
    for index, text in enumerate(texts):
        status_index = int(status_probs[index].argmax().item())
        status = STATUS_LABELS[status_index]
        critical = [float(status_probs[index, status_index].item())]
        if status != ParseStatus.SUPPORTED:
            error_index = int(error_probs[index].argmax().item())
            critical.append(float(error_probs[index, error_index].item()))
            scores = _confidence_scores(critical)
            proposal = LanguageProposal(
                status,
                languages[index],
                text,
                issues=(
                    ValidationIssue(
                        ERROR_LABELS[error_index],
                        "language",
                        "Factorized parser abstention",
                    ),
                ),
                confidence=scores["minimum"],
                parser_name="factorized_typed_v2",
            )
            predictions.append(StructuredPrediction(proposal, scores, False))
            continue
        family_index = int(family_probs[index].argmax().item())
        family = FAMILY_LABELS[family_index]
        critical.append(float(family_probs[index, family_index].item()))
        count_index = int(count_probs[index].argmax().item())
        critical.append(float(count_probs[index, count_index].item()))
        required_count = _required_source_count(family)
        source_ids = []
        for slot in range(required_count):
            source_id = int(source_probs[index, slot].argmax().item())
            source_ids.append(source_id)
            critical.append(float(source_probs[index, slot, source_id].item()))
        destination_index = int(destination_probs[index].argmax().item())
        critical.append(float(destination_probs[index, destination_index].item()))
        preserve = []
        termination = []
        for variable_index, variable in enumerate(VARIABLES):
            present, field_confidence = _predicted_binary_confidence(
                logits["preserve"][index, variable_index]
            )
            critical.append(field_confidence)
            if present:
                preserve.append(variable)
            present, field_confidence = _predicted_binary_confidence(
                logits["termination"][index, variable_index]
            )
            critical.append(field_confidence)
            if present:
                termination.append(variable)
        order_index = int(order_probs[index].argmax().item())
        if family == SemanticFamily.DROP_THEN_TRANSFER:
            critical.append(float(order_probs[index, order_index].item()))
        scores = _confidence_scores(critical)
        invalid = None
        try:
            if count_index != required_count:
                raise ValueError(
                    f"source-count head predicted {count_index}, family requires {required_count}"
                )
            if len(set(source_ids)) != len(source_ids):
                raise ValueError("source-role heads selected duplicate variables")
            needs_destination = family not in {
                SemanticFamily.NOOP,
                SemanticFamily.CLEAR,
            }
            if needs_destination != (destination_index < len(VARIABLES)):
                raise ValueError("destination head disagrees with semantic family")
            if family == SemanticFamily.DROP_THEN_TRANSFER and order_index != 0:
                raise ValueError("order head reversed the required phase order")
            sources = tuple(VARIABLES[value] for value in source_ids)
            destination = (
                VARIABLES[destination_index]
                if destination_index < len(VARIABLES)
                else None
            )
            base = build_family_specification(
                family, sources=sources, destination=destination
            )
            specification = replace(
                base,
                preserve=tuple(sorted(preserve)),
                terminate_when_empty=tuple(termination),
            )
            issues = validate_specification(specification)
            if issues:
                raise ValueError(str(issues[0].code))
            proposal = LanguageProposal(
                ParseStatus.SUPPORTED,
                languages[index],
                text,
                specification,
                family,
                confidence=scores["minimum"],
                parser_name="factorized_typed_v2",
            )
        except (ValueError, IndexError, KeyError) as exc:
            invalid = str(exc)
            proposal = _invalid_proposal(
                text,
                languages[index],
                scores["minimum"],
                invalid,
                parser_name="factorized_typed_v2",
            )
        predictions.append(StructuredPrediction(proposal, scores, True, invalid))
    return predictions


@torch.no_grad()
def predict_raw(
    model: nn.Module,
    texts: Sequence[str],
    languages: Sequence[str],
    *,
    config: FairParserConfig,
    device: torch.device,
    tokenizer: ByteLevelBpeTokenizer | None = None,
) -> list[StructuredPrediction]:
    model.eval()
    ids, mask, _ = encode_texts_v2(
        texts, config=config, device=device, tokenizer=tokenizer
    )
    logits = model(ids, mask)
    if config.candidate_kind == "catalog":
        return _decode_catalog(logits, texts, languages, catalog_answers())
    return _decode_factorized(logits, texts, languages)


def _target_spec(row: dict[str, Any]) -> ProgramSpecification | None:
    payload = row["canonical_specification"]
    return ProgramSpecification(**payload) if payload is not None else None


def prediction_correct(
    prediction: StructuredPrediction, row: dict[str, Any], *, semantic: bool
) -> bool:
    proposal = prediction.proposal
    if str(proposal.status) != row["status"]:
        return False
    target = _target_spec(row)
    if target is None:
        return bool(
            proposal.issues and str(proposal.issues[0].code) == row["error_code"]
        )
    if proposal.specification is None:
        return False
    comparator = (
        semantic_specification_equal if semantic else structural_specification_equal
    )
    return comparator(proposal.specification, target)


def apply_calibration(
    prediction: StructuredPrediction,
    calibration: CalibrationResult | None,
) -> StructuredPrediction:
    if not prediction.raw_supported:
        return prediction
    if calibration is None:
        return prediction
    if calibration.status != "CALIBRATED" or calibration.threshold is None:
        proposal = _invalid_proposal(
            prediction.proposal.original_text,
            prediction.proposal.language,
            0.0,
            "Calibration failed closed; trusted review is required",
            parser_name=prediction.proposal.parser_name,
        )
        return StructuredPrediction(
            proposal, prediction.confidence_scores, True, "CALIBRATION_FAILED"
        )
    score = prediction.confidence_scores[calibration.method]
    if score < calibration.threshold:
        proposal = LanguageProposal(
            ParseStatus.AMBIGUOUS,
            prediction.proposal.language,
            prediction.proposal.original_text,
            issues=(
                ValidationIssue(
                    ValidationCode.LOW_CONFIDENCE,
                    "confidence",
                    "Critical-field confidence is below the calibrated threshold",
                ),
            ),
            confidence=score,
            parser_name=prediction.proposal.parser_name,
        )
        return StructuredPrediction(proposal, prediction.confidence_scores, True)
    return replace(
        prediction,
        proposal=replace(prediction.proposal, confidence=score),
    )


def _group_metrics(
    rows: Sequence[dict[str, Any]],
    correct: Sequence[bool],
    accepted: Sequence[bool],
    getter: Any,
) -> dict[str, Any]:
    groups: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        groups[str(getter(row))].append(index)
    return {
        key: {
            "count": len(indices),
            "semantic_exact": sum(correct[index] for index in indices) / len(indices),
            "coverage": sum(accepted[index] for index in indices) / len(indices),
            "incorrect_accepted_rate": sum(
                accepted[index] and not correct[index] for index in indices
            )
            / len(indices),
        }
        for key, indices in sorted(groups.items())
    }


@torch.no_grad()
def evaluate_candidate(
    model: nn.Module,
    rows: Sequence[dict[str, Any]],
    *,
    config: FairParserConfig,
    device: torch.device,
    calibration: CalibrationResult | None,
    batch_size: int = 128,
    retain_failures: int = 50,
) -> dict[str, Any]:
    tokenizer = _tokenizer(config)
    predictions: list[StructuredPrediction] = []
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        raw = predict_raw(
            model,
            [row["text"] for row in batch],
            [row["language"] for row in batch],
            config=config,
            device=device,
            tokenizer=tokenizer,
        )
        predictions.extend(apply_calibration(item, calibration) for item in raw)
    structural = [
        prediction_correct(prediction, row, semantic=False)
        for prediction, row in zip(predictions, rows, strict=True)
    ]
    semantic = [
        prediction_correct(prediction, row, semantic=True)
        for prediction, row in zip(predictions, rows, strict=True)
    ]
    accepted = [
        prediction.proposal.status == ParseStatus.SUPPORTED
        for prediction in predictions
    ]
    accepted_count = sum(accepted)
    false_accepted = sum(
        accept and not correct
        for accept, correct in zip(accepted, semantic, strict=True)
    )
    status_accuracy = [
        str(prediction.proposal.status) == row["status"]
        for prediction, row in zip(predictions, rows, strict=True)
    ]
    group_dimensions = {
        "language": lambda row: row["language"],
        "family": lambda row: row["semantic_family"],
        "language_family": lambda row: f"{row['language']}|{row['semantic_family']}",
        "role_assignment": lambda row: row["metadata"].get("role_assignment"),
        "status": lambda row: row["status"],
        "error_code": lambda row: row["error_code"],
    }
    failures = []
    for prediction, row, is_correct in zip(predictions, rows, semantic, strict=True):
        if is_correct or len(failures) >= retain_failures:
            continue
        failures.append(
            {
                "text": row["text"],
                "language": row["language"],
                "family": row["semantic_family"],
                "role_assignment": row["metadata"].get("role_assignment"),
                "target_status": row["status"],
                "predicted_status": str(prediction.proposal.status),
                "target_error": row["error_code"],
                "predicted_error": (
                    str(prediction.proposal.issues[0].code)
                    if prediction.proposal.issues
                    else None
                ),
                "invalid_reason": prediction.invalid_reason,
                "confidence": prediction.proposal.confidence,
            }
        )
    return {
        "count": len(rows),
        "structural_specification_exact": sum(structural) / max(1, len(rows)),
        "semantic_specification_exact": sum(semantic) / max(1, len(rows)),
        "status_accuracy": sum(status_accuracy) / max(1, len(rows)),
        "coverage": accepted_count / max(1, len(rows)),
        "accepted_count": accepted_count,
        "accepted_precision": sum(
            correct
            for correct, accept in zip(semantic, accepted, strict=True)
            if accept
        )
        / max(1, accepted_count),
        "incorrect_accepted_rate": false_accepted / max(1, len(rows)),
        "conditional_accepted_risk": false_accepted / max(1, accepted_count),
        "calibration_status": (
            calibration.status if calibration is not None else "UNCALIBRATED"
        ),
        "groups": {
            key: _group_metrics(rows, semantic, accepted, getter)
            for key, getter in group_dimensions.items()
        },
        "input_lengths": input_length_statistics(rows, config),
        "failures": failures,
    }


@torch.no_grad()
def calibrate_fail_closed(
    model: nn.Module,
    rows: Sequence[dict[str, Any]],
    *,
    config: FairParserConfig,
    device: torch.device,
    max_conditional_risk: float = 0.01,
) -> CalibrationResult:
    tokenizer = _tokenizer(config)
    predictions: list[StructuredPrediction] = []
    for start in range(0, len(rows), 128):
        batch = rows[start : start + 128]
        predictions.extend(
            predict_raw(
                model,
                [row["text"] for row in batch],
                [row["language"] for row in batch],
                config=config,
                device=device,
                tokenizer=tokenizer,
            )
        )
    correct = [
        prediction_correct(prediction, row, semantic=True)
        for prediction, row in zip(predictions, rows, strict=True)
    ]
    supported_indices = [
        index
        for index, prediction in enumerate(predictions)
        if prediction.raw_supported
    ]
    temperature = 1.0
    if supported_indices:
        best_loss = float("inf")
        for candidate in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0):
            losses = []
            for index in supported_indices:
                product = predictions[index].confidence_scores["product"]
                product = min(1.0 - 1e-7, max(1e-7, product))
                logit = math.log(product / (1.0 - product)) / candidate
                probability = 1.0 / (1.0 + math.exp(-logit))
                target = float(correct[index])
                losses.append(
                    -(target * math.log(probability + 1e-9))
                    - ((1.0 - target) * math.log(1.0 - probability + 1e-9))
                )
            candidate_loss = mean(losses)
            if candidate_loss < best_loss:
                best_loss = candidate_loss
                temperature = candidate
        for index in supported_indices:
            scores = _confidence_scores(
                [predictions[index].confidence_scores["product"]], temperature
            )
            predictions[index].confidence_scores["temperature_joint"] = scores[
                "temperature_joint"
            ]
    full_curve = []
    best: tuple[float, ConfidenceMethod, float, float, int] | None = None
    for method in ("product", "minimum", "temperature_joint"):
        scores = sorted(
            {
                predictions[index].confidence_scores[method]
                for index in supported_indices
            },
            reverse=True,
        )
        thresholds = sorted(
            {0.0, 0.5, 0.7, 0.8, 0.9, 0.95, 0.97, 0.99, *scores},
            reverse=True,
        )
        for threshold in thresholds:
            accepted = [
                index
                for index in supported_indices
                if predictions[index].confidence_scores[method] >= threshold
            ]
            false = sum(not correct[index] for index in accepted)
            risk = false / max(1, len(accepted))
            coverage = len(accepted) / max(1, len(rows))
            precision = sum(correct[index] for index in accepted) / max(
                1, len(accepted)
            )
            full_curve.append(
                {
                    "method": method,
                    "threshold": threshold,
                    "coverage": coverage,
                    "accepted_count": len(accepted),
                    "accepted_precision": precision,
                    "conditional_risk": risk,
                    "incorrect_accepted_rate": false / max(1, len(rows)),
                }
            )
            if len(accepted) and risk <= max_conditional_risk:
                candidate = (coverage, method, threshold, precision, len(accepted))
                if best is None or candidate[0] > best[0]:
                    best = candidate
    if best is None:
        return CalibrationResult(
            "FAILED",
            "minimum",
            None,
            temperature,
            0.0,
            0.0,
            0,
            tuple(full_curve),
        )
    coverage, method, threshold, precision, accepted_count = best
    return CalibrationResult(
        "CALIBRATED",
        method,
        threshold,
        temperature,
        coverage,
        precision,
        accepted_count,
        tuple(full_curve),
    )


class BalancedBatchSampler:
    def __init__(
        self,
        rows: Sequence[dict[str, Any]],
        seed: int,
        *,
        clause_shuffle_probability: float = 0.0,
    ) -> None:
        groups: dict[tuple[str, str, str, str], list[int]] = defaultdict(list)
        for index, row in enumerate(rows):
            groups[
                (
                    row["language"],
                    row["status"],
                    str(row["semantic_family"]),
                    str(row["metadata"].get("role_assignment")),
                )
            ].append(index)
        self.rows = rows
        self.groups = groups
        self.keys = tuple(groups)
        self.rng = random.Random(seed)
        self.sampled = Counter()
        self.clause_shuffle_probability = clause_shuffle_probability

    def batch(self, size: int) -> list[dict[str, Any]]:
        batch = []
        for _ in range(size):
            key = self.rng.choice(self.keys)
            row = self.rows[self.rng.choice(self.groups[key])]
            self.sampled[key] += 1
            augmented = role_permutation_augment(row, self.rng)
            batch.append(
                clause_order_augment(
                    augmented,
                    self.rng,
                    probability=self.clause_shuffle_probability,
                )
            )
        return batch

    def distribution(self) -> dict[str, int]:
        return {"|".join(key): count for key, count in sorted(self.sampled.items())}


def _paired_rows(
    rows: Sequence[dict[str, Any]], rng: random.Random, pair_count: int
) -> list[dict[str, Any]]:
    pairs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        pair_id = row["metadata"].get("pair_id")
        if pair_id and row["status"] == str(ParseStatus.SUPPORTED):
            pairs[str(pair_id)].append(row)
    valid = [pair for pair in pairs.values() if len(pair) == 2]
    if not valid:
        return []
    selected = []
    for _ in range(pair_count):
        selected.extend(rng.choice(valid))
    return selected


def paired_consistency_loss(
    logits: dict[str, torch.Tensor], rows: Sequence[dict[str, Any]]
) -> torch.Tensor:
    pairs: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        pair_id = row["metadata"].get("pair_id")
        if pair_id:
            pairs[str(pair_id)].append(index)
    losses = []
    for indices in pairs.values():
        if len(indices) != 2:
            continue
        left, right = indices
        losses.extend(
            F.mse_loss(values[left], values[right]) for values in logits.values()
        )
    if not losses:
        return next(iter(logits.values())).new_zeros(())
    return torch.stack(losses).mean()


def _rename_value(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [_rename_value(item, mapping) for item in value]
    if isinstance(value, tuple):
        return tuple(_rename_value(item, mapping) for item in value)
    if isinstance(value, dict):
        return {key: _rename_value(item, mapping) for key, item in value.items()}
    return value


def role_permutation_augment(
    row: dict[str, Any], rng: random.Random, probability: float = 0.5
) -> dict[str, Any]:
    if rng.random() >= probability:
        return row
    family_name = row.get("semantic_family")
    if row["status"] != str(ParseStatus.SUPPORTED) or family_name is None:
        return row
    family = SemanticFamily(family_name)
    assignment = tuple(row["metadata"]["assignment"])
    allowed = set(assignments_for(family, holdout=False))
    for _ in range(32):
        shuffled = list(VARIABLES)
        rng.shuffle(shuffled)
        mapping = dict(zip(VARIABLES, shuffled, strict=True))
        permuted_assignment = tuple(mapping[value] for value in assignment)
        if permuted_assignment not in allowed:
            continue
        updated = copy.deepcopy(row)
        placeholders = {key: f"__ROLE_{key}__" for key in VARIABLES}
        text = updated["text"]
        for source, placeholder in placeholders.items():
            text = re.sub(rf"\b{source}\b", placeholder, text)
        for source, placeholder in placeholders.items():
            text = text.replace(placeholder, mapping[source])
        updated["text"] = text
        updated["prompt"] = text
        updated["canonical_specification"] = _rename_value(
            updated["canonical_specification"], mapping
        )
        updated["metadata"]["assignment"] = list(permuted_assignment)
        updated["metadata"]["role_assignment"] = "".join(permuted_assignment) or "NONE"
        spec = ProgramSpecification(**updated["canonical_specification"])
        updated["answer"] = json.dumps(
            {
                "specification": asdict(canonicalize_specification(spec)),
                "status": str(ParseStatus.SUPPORTED),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return updated
    return row


def clause_order_augment(
    row: dict[str, Any], rng: random.Random, *, probability: float = 0.5
) -> dict[str, Any]:
    """Shuffle complete surface clauses while preserving each clause verbatim."""
    if probability <= 0 or rng.random() >= probability:
        return row
    clauses = [
        match.group(0).strip()
        for match in re.finditer(r"[^.!?;]+[.!?;]?", row["text"])
        if match.group(0).strip()
    ]
    if len(clauses) < 3:
        return row
    shuffled = list(clauses)
    rng.shuffle(shuffled)
    if shuffled == clauses:
        shuffled = [*clauses[1:], clauses[0]]
    updated = copy.deepcopy(row)
    updated["text"] = " ".join(shuffled)
    updated["prompt"] = updated["text"]
    return updated


def build_candidate(
    config: FairParserConfig,
) -> CatalogSpecificationClassifier | FactorizedLanguageToSpecParserV2:
    if config.candidate_kind == "catalog":
        return CatalogSpecificationClassifier(config, len(catalog_answers()))
    return FactorizedLanguageToSpecParserV2(config)


def make_config(
    *,
    candidate_kind: CandidateKind,
    encoding: EncodingMode,
    tokenizer_path: Path | None,
    max_length: int | None = None,
) -> FairParserConfig:
    if encoding == "byte":
        return FairParserConfig(
            candidate_kind,
            encoding,
            vocab_size=258,
            max_length=max_length or 768,
        )
    if tokenizer_path is None:
        raise ValueError("BPE config requires a tokenizer")
    tokenizer = ByteLevelBpeTokenizer.load(tokenizer_path)
    return FairParserConfig(
        candidate_kind,
        encoding,
        vocab_size=tokenizer.vocab_size,
        max_length=max_length or 256,
        tokenizer_path=str(tokenizer_path),
    )


def train_fair_candidate(
    *,
    train_path: Path,
    validation_path: Path,
    calibration_path: Path,
    output_dir: Path,
    config: FairParserConfig,
    seed: int,
    max_steps: int = 20_000,
    batch_size: int = 64,
    learning_rate: float = 3e-4,
    eval_every: int = 500,
    patience: int = 4,
    consistency_weight: float = 0.0,
    clause_shuffle_probability: float = 0.0,
    cpu: bool = False,
) -> dict[str, Any]:
    device_info = get_device_info(prefer_cuda=not cpu)
    device = device_info.device
    torch.manual_seed(seed)
    random.seed(seed)
    if device_info.is_cuda:
        torch.cuda.manual_seed_all(seed)
    train_rows = load_language_rows(train_path)
    validation_rows = load_language_rows(validation_path)
    calibration_rows = load_language_rows(calibration_path)
    for split_name, rows in (
        ("train", train_rows),
        ("validation", validation_rows),
        ("calibration", calibration_rows),
    ):
        stats = input_length_statistics(rows, config)
        if stats["truncated"]:
            raise InputTooLongError(
                f"{split_name} has {stats['truncated']} overlength examples"
            )
    model = build_candidate(config).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=learning_rate, weight_decay=0.01
    )
    tokenizer = _tokenizer(config)
    sampler = BalancedBatchSampler(
        train_rows,
        seed,
        clause_shuffle_probability=clause_shuffle_probability,
    )
    pair_rng = random.Random(seed + 91_003)
    catalog = catalog_answers()
    history = []
    best_state = copy.deepcopy(model.state_dict())
    best_score = -1.0
    best_step = 0
    stale_evaluations = 0
    started = time.perf_counter()
    for step in range(1, max_steps + 1):
        model.train()
        batch = sampler.batch(batch_size)
        if consistency_weight > 0:
            paired = _paired_rows(train_rows, pair_rng, min(8, batch_size // 2))
            if paired:
                batch[-len(paired) :] = paired
        ids, mask, _ = encode_texts_v2(
            [row["text"] for row in batch],
            config=config,
            device=device,
            tokenizer=tokenizer,
        )
        logits = model(ids, mask)
        if config.candidate_kind == "catalog":
            labels = torch.tensor(
                [_catalog_label(row, catalog) for row in batch],
                dtype=torch.long,
                device=device,
            )
            loss = F.cross_entropy(logits["catalog"], labels)
        else:
            loss = factorized_loss(logits, _factorized_labels(batch, device))
        if consistency_weight > 0:
            loss = loss + consistency_weight * paired_consistency_loss(logits, batch)
        if not torch.isfinite(loss):
            raise ValueError(f"Non-finite M-23.1 loss at step {step}")
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        if step % eval_every != 0 and step != max_steps:
            continue
        validation = evaluate_candidate(
            model,
            validation_rows,
            config=config,
            device=device,
            calibration=None,
            retain_failures=0,
        )
        score = (
            validation["semantic_specification_exact"]
            - validation["incorrect_accepted_rate"]
        )
        history.append(
            {
                "step": step,
                "train_loss": float(loss.detach().cpu().item()),
                "grad_norm": float(grad_norm.detach().cpu().item()),
                "validation_semantic_exact": validation["semantic_specification_exact"],
                "validation_status_accuracy": validation["status_accuracy"],
                "selection_score": score,
            }
        )
        if score > best_score + 1e-6:
            best_score = score
            best_step = step
            best_state = copy.deepcopy(model.state_dict())
            stale_evaluations = 0
        else:
            stale_evaluations += 1
        if stale_evaluations >= patience:
            break
    model.load_state_dict(best_state)
    calibration = calibrate_fail_closed(
        model, calibration_rows, config=config, device=device
    )
    train_subset = evaluate_candidate(
        model,
        train_rows[: min(2_000, len(train_rows))],
        config=config,
        device=device,
        calibration=calibration,
        retain_failures=0,
    )
    validation = evaluate_candidate(
        model,
        validation_rows,
        config=config,
        device=device,
        calibration=calibration,
        retain_failures=50,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "best.pt"
    payload = {
        "model_state_dict": model.state_dict(),
        "config": asdict(config),
        "seed": seed,
        "best_step": best_step,
        "calibration": asdict(calibration),
    }
    torch.save(payload, checkpoint_path)
    result = {
        "checkpoint": str(checkpoint_path),
        "seed": seed,
        "best_step": best_step,
        "updates_run": history[-1]["step"] if history else 0,
        "processed_examples": (history[-1]["step"] if history else 0) * batch_size,
        "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        "wall_time_seconds": time.perf_counter() - started,
        "device": str(device),
        "device_name": device_info.name,
        "config": asdict(config),
        "history": history,
        "balanced_sampler_distribution": sampler.distribution(),
        "pair_consistency_weight": consistency_weight,
        "clause_shuffle_probability": clause_shuffle_probability,
        "calibration": asdict(calibration),
        "train_subset": {
            key: value for key, value in train_subset.items() if key != "failures"
        },
        "validation": validation,
        "input_lengths": {
            "train": input_length_statistics(train_rows, config),
            "validation": input_length_statistics(validation_rows, config),
            "calibration": input_length_statistics(calibration_rows, config),
        },
    }
    (output_dir / "train_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return result


def load_fair_candidate(
    checkpoint_path: Path, *, device: torch.device
) -> tuple[nn.Module, FairParserConfig, CalibrationResult, dict[str, Any]]:
    payload = torch.load(checkpoint_path, map_location=device)
    config = FairParserConfig(**payload["config"])
    model = build_candidate(config)
    model.load_state_dict(payload["model_state_dict"])
    model.to(device).eval()
    calibration = CalibrationResult(**payload["calibration"])
    return model, config, calibration, payload
