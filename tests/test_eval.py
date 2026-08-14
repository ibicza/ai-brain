from __future__ import annotations

import json
from dataclasses import asdict
from types import SimpleNamespace

import torch

from ai_brain.cli import main
from ai_brain.eval.final_answer import (
    extract_final_answer,
    final_answers_match,
    normalize_final_answer,
)
from ai_brain.eval.generation import generate_greedy, load_model_for_inference
from ai_brain.eval.metrics import summarize_predictions
from ai_brain.eval.normalize import (
    extract_generated_answer,
    is_false_answer,
    normalize_answer,
)
from ai_brain.eval.runner import eval_lm
from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.language.tokenizer.special_tokens import END_TOKEN, EOS_TOKEN
from ai_brain.language.tokenizer.text_format import format_prompt_answer
from ai_brain.model.config import (
    ModelConfig,
    numeric_debug_config,
    recurrent_debug_config,
)
from ai_brain.model.factory import build_model
from ai_brain.model.recurrent_transformer import RecurrentCausalTransformer
from ai_brain.model.tiny_transformer import (
    TinyCausalTransformer,
    TinyNumericCausalTransformer,
)


def _records() -> list[dict[str, str]]:
    return [
        {
            "id": "add:1",
            "task_type": "arithmetic.add",
            "prompt": "Add 2 + 3.",
            "answer": "5",
        },
        {
            "id": "unk:1",
            "task_type": "epistemic.insufficient_info",
            "prompt": "How many apples does Masha have?",
            "answer": "Недостаточно информации",
        },
    ]


def _write_jsonl(path, records: list[dict[str, str]]) -> None:
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records),
        encoding="utf-8",
    )


def _make_tokenizer_and_checkpoint(tmp_path):
    tokenizer_path = tmp_path / "tokenizer.json"
    checkpoint_path = tmp_path / "checkpoint.pt"
    tokenizer = ByteLevelBpeTokenizer.train(
        [
            format_prompt_answer(record["prompt"], record["answer"])
            for record in _records()
        ],
        vocab_size=512,
        min_frequency=1,
    )
    tokenizer.save(tokenizer_path)

    model_config = ModelConfig(
        vocab_size=tokenizer.vocab_size,
        max_sequence_length=32,
        d_model=32,
        num_layers=1,
        num_heads=4,
        ffn_hidden_dim=64,
        dropout=0.0,
        tie_embeddings=True,
    )
    model = TinyCausalTransformer(model_config)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    torch.save(
        {
            "step": 1,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "model_config": asdict(model_config),
            "train_config": {"loss_mode": "answer-only"},
            "tokenizer_path": str(tokenizer_path),
            "last_metrics": {"train_loss": 1.0},
        },
        checkpoint_path,
    )
    return tokenizer_path, checkpoint_path


def test_normalize_answer() -> None:
    assert normalize_answer("  Нет. ") == "нет"
    assert normalize_answer("Да.") == "да"
    assert normalize_answer("  5  ") == "5"
    assert normalize_answer("Ёж   идет") == "еж идет"


def test_extract_generated_answer_until_end() -> None:
    assert extract_generated_answer(f"5\n{END_TOKEN}") == "5"
    assert extract_generated_answer(f"<|answer|> 7 \n{EOS_TOKEN}") == "7"


def test_extract_final_answer_falls_back_to_normal_answer() -> None:
    assert extract_final_answer("  134  ") == "134"


def test_extract_final_answer_uses_answer_marker() -> None:
    assert extract_final_answer("ones: 1 + 3 = 4\nanswer: 134") == "134"


def test_extract_final_answer_last_marker_wins() -> None:
    text = "answer: 120\ntrace corrected\nFINAL: 134"

    assert extract_final_answer(text) == "134"


def test_extract_final_answer_uses_out_marker() -> None:
    text = "P0 1 3 C0 -> S4 C0\nOUT 1 3 4"

    assert extract_final_answer(text) == "1 3 4"


def test_extract_final_answer_stops_at_special_token() -> None:
    text = f"OUT 1 3 4\n{END_TOKEN}\nOUT 0"

    assert extract_final_answer(text) == "1 3 4"


def test_final_normalization_matches_digit_spaced_single_number() -> None:
    assert normalize_final_answer("1 3 4") == "134"
    assert final_answers_match("answer: 134", "OUT 1 3 4")


def test_final_normalization_matches_role_tagged_single_number() -> None:
    assert extract_final_answer("OUT_T 7 OUT_U 3") == "OUT_T 7 OUT_U 3"
    assert normalize_final_answer("OUT_T 7 OUT_U 3") == "73"
    assert normalize_final_answer("OUT_H 1 OUT_T 3 OUT_U 4") == "134"
    assert final_answers_match("answer: 73", "OUT_T 7 OUT_U 3")
    assert final_answers_match("answer: 73", "7 3")


def test_final_normalization_does_not_collapse_sorting_list() -> None:
    assert normalize_final_answer("1, 3, 4") == "1, 3, 4"
    assert normalize_final_answer("OUT 26, 27, 34, 78") == "out 26, 27, 34, 78"
    assert not final_answers_match("OUT 134", "OUT 1, 3, 4")
    assert not final_answers_match("OUT 26273478", "OUT 26, 27, 34, 78")


def test_scratchpad_final_answer_matches_with_different_trace() -> None:
    expected = "ones: 1 + 3 = 4\ntens: 7 + 6 = 13\nanswer: 134"
    predicted = "ones: wrong\ntens: wrong\nanswer: 134"

    assert final_answers_match(expected, predicted)


def test_scratchpad_final_answer_detects_wrong_final() -> None:
    expected = "ones: 1 + 3 = 4\nanswer: 134"
    predicted = "ones: 1 + 3 = 4\nanswer: 135"

    assert not final_answers_match(expected, predicted)


def test_generate_greedy_stops_on_end_or_eos() -> None:
    class DummyModel:
        def __init__(self) -> None:
            self.config = SimpleNamespace(max_sequence_length=8)
            self.training = True
            self.calls = 0

        def eval(self) -> None:
            self.training = False

        def train(self) -> None:
            self.training = True

        def __call__(self, input_ids):
            self.calls += 1
            logits = torch.zeros((1, input_ids.shape[1], 10))
            logits[:, -1, 6] = 1.0
            return logits

    model = DummyModel()
    generated = generate_greedy(
        model,
        torch.tensor([[1, 2]], dtype=torch.long),
        max_new_tokens=5,
        eos_token_id=2,
        end_token_id=6,
    )

    assert generated == [6]
    assert model.training is True
    assert model.calls == 1


def test_load_checkpoint_model_for_inference(tmp_path) -> None:
    tokenizer_path, checkpoint_path = _make_tokenizer_and_checkpoint(tmp_path)

    model, checkpoint = load_model_for_inference(
        checkpoint_path=checkpoint_path,
        tokenizer_path=tokenizer_path,
        device=torch.device("cpu"),
    )

    assert isinstance(model, TinyCausalTransformer)
    assert model.training is False
    assert checkpoint["step"] == 1


def test_load_old_checkpoint_without_model_type_for_inference(tmp_path) -> None:
    tokenizer_path, checkpoint_path = _make_tokenizer_and_checkpoint(tmp_path)
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    checkpoint["model_config"].pop("model_type", None)
    torch.save(checkpoint, checkpoint_path)

    model, loaded_checkpoint = load_model_for_inference(
        checkpoint_path=checkpoint_path,
        tokenizer_path=tokenizer_path,
        device=torch.device("cpu"),
    )

    assert isinstance(model, TinyCausalTransformer)
    assert model.training is False
    assert loaded_checkpoint["step"] == 1


def test_load_numeric_checkpoint_for_inference_and_eval(tmp_path) -> None:
    records = [
        {
            "id": "digit:add",
            "task_type": "arithmetic.digit_add_no_carry",
            "prompt": "case 1. ADD_DIGIT a=3 b=4 c=0",
            "answer": "S 7 C 0",
        }
    ]
    tokenizer_path = tmp_path / "tokenizer.json"
    checkpoint_path = tmp_path / "numeric_checkpoint.pt"
    eval_path = tmp_path / "eval.jsonl"
    output_dir = tmp_path / "eval_numeric"
    tokenizer = ByteLevelBpeTokenizer.train(
        [
            format_prompt_answer(record["prompt"], record["answer"])
            for record in records
        ],
        vocab_size=512,
        min_frequency=1,
    )
    tokenizer.save(tokenizer_path)
    _write_jsonl(eval_path, records)

    base_config = numeric_debug_config()
    model_config = ModelConfig(
        **{
            **asdict(base_config),
            "vocab_size": tokenizer.vocab_size,
            "max_sequence_length": 64,
        }
    )
    model = build_model(model_config)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    torch.save(
        {
            "step": 1,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "model_config": asdict(model_config),
            "train_config": {"loss_mode": "answer-only"},
            "tokenizer_path": str(tokenizer_path),
            "last_metrics": {"train_loss": 1.0},
        },
        checkpoint_path,
    )

    loaded_model, checkpoint = load_model_for_inference(
        checkpoint_path=checkpoint_path,
        tokenizer_path=tokenizer_path,
        device=torch.device("cpu"),
    )
    result = eval_lm(
        checkpoint_path=checkpoint_path,
        eval_path=eval_path,
        tokenizer_path=tokenizer_path,
        output_dir=output_dir,
        max_examples=1,
        max_new_tokens=2,
        cpu=True,
    )

    assert isinstance(loaded_model, TinyNumericCausalTransformer)
    assert checkpoint["model_config"]["model_type"] == "numeric"
    assert result["summary"]["count"] == 1
    assert (output_dir / "predictions.jsonl").exists()


def test_load_recurrent_checkpoint_for_inference(tmp_path) -> None:
    tokenizer_path = tmp_path / "tokenizer.json"
    checkpoint_path = tmp_path / "recurrent_checkpoint.pt"
    tokenizer = ByteLevelBpeTokenizer.train(
        [
            format_prompt_answer(record["prompt"], record["answer"])
            for record in _records()
        ],
        vocab_size=512,
        min_frequency=1,
    )
    tokenizer.save(tokenizer_path)

    model_config = recurrent_debug_config()
    model_config = ModelConfig(
        **{
            **asdict(model_config),
            "vocab_size": tokenizer.vocab_size,
            "max_sequence_length": 32,
        }
    )
    model = build_model(model_config)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    torch.save(
        {
            "step": 1,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "model_config": asdict(model_config),
            "train_config": {"loss_mode": "answer-only"},
            "tokenizer_path": str(tokenizer_path),
            "last_metrics": {"train_loss": 1.0},
        },
        checkpoint_path,
    )

    loaded_model, checkpoint = load_model_for_inference(
        checkpoint_path=checkpoint_path,
        tokenizer_path=tokenizer_path,
        device=torch.device("cpu"),
    )

    assert isinstance(loaded_model, RecurrentCausalTransformer)
    assert loaded_model.training is False
    assert checkpoint["model_config"]["model_type"] == "recurrent"


def test_eval_lm_writes_predictions_and_summary(tmp_path) -> None:
    tokenizer_path, checkpoint_path = _make_tokenizer_and_checkpoint(tmp_path)
    eval_path = tmp_path / "eval.jsonl"
    output_dir = tmp_path / "eval_run"
    _write_jsonl(eval_path, _records())

    result = eval_lm(
        checkpoint_path=checkpoint_path,
        eval_path=eval_path,
        tokenizer_path=tokenizer_path,
        output_dir=output_dir,
        max_examples=2,
        max_new_tokens=2,
        cpu=True,
    )

    predictions = (
        (output_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
    )
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))

    assert result["summary"]["count"] == 2
    first_prediction = json.loads(predictions[0])

    assert len(predictions) == 2
    assert summary["overall"]["count"] == 2
    assert "final_normalized_exact_match" in summary["overall"]
    assert "final_expected" in first_prediction
    assert "final_predicted" in first_prediction
    assert "final_normalized_exact_match" in first_prediction
    assert "arithmetic.add" in summary["by_task_type"]
    assert "epistemic" in summary


def test_eval_metrics_by_task_type() -> None:
    summary = summarize_predictions(
        [
            {
                "task_type": "arithmetic.add",
                "task_group": "arithmetic",
                "exact_match": True,
                "normalized_exact_match": True,
                "false_answer": False,
            },
            {
                "task_type": "arithmetic.add",
                "task_group": "arithmetic",
                "exact_match": False,
                "normalized_exact_match": False,
                "false_answer": False,
            },
        ]
    )

    assert summary["overall"]["exact_match"] == 0.5
    assert summary["overall"]["final_normalized_exact_match"] == 0.5
    assert summary["by_group"]["arithmetic"]["count"] == 2
    assert summary["by_task_type"]["arithmetic.add"]["normalized_exact_match"] == 0.5


def test_false_answer_rate_for_epistemic_tasks() -> None:
    assert is_false_answer(
        task_type="epistemic.insufficient_info",
        expected="Недостаточно информации",
        predicted="7",
    )
    assert not is_false_answer(
        task_type="epistemic.insufficient_info",
        expected="Недостаточно информации",
        predicted="Недостаточно информации",
    )


def test_generate_answer_cli(tmp_path, capsys) -> None:
    tokenizer_path, checkpoint_path = _make_tokenizer_and_checkpoint(tmp_path)

    exit_code = main(
        [
            "generate-answer",
            "--checkpoint",
            str(checkpoint_path),
            "--tokenizer",
            str(tokenizer_path),
            "--prompt",
            "Add 2 + 3.",
            "--max-new-tokens",
            "2",
            "--cpu",
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert result["prompt"] == "Add 2 + 3."
    assert "answer" in result
    assert result["tokens_generated"] <= 2


def test_eval_lm_cli(tmp_path, capsys) -> None:
    tokenizer_path, checkpoint_path = _make_tokenizer_and_checkpoint(tmp_path)
    eval_path = tmp_path / "eval.jsonl"
    output_dir = tmp_path / "eval_run"
    _write_jsonl(eval_path, _records())

    exit_code = main(
        [
            "eval-lm",
            "--checkpoint",
            str(checkpoint_path),
            "--eval",
            str(eval_path),
            "--tokenizer",
            str(tokenizer_path),
            "--output-dir",
            str(output_dir),
            "--max-examples",
            "2",
            "--max-new-tokens",
            "2",
            "--cpu",
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert result["summary"]["count"] == 2
    assert (output_dir / "predictions.jsonl").exists()
    assert (output_dir / "summary.json").exists()
