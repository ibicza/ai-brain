from __future__ import annotations

import json

from ai_brain.language.tokenizer.bpe_tokenizer import ByteLevelBpeTokenizer
from ai_brain.language.tokenizer.io import iter_tokenizer_texts_from_path
from ai_brain.language.tokenizer.special_tokens import SPECIAL_TOKEN_IDS, SPECIAL_TOKENS
from ai_brain.language.tokenizer.text_format import format_prompt_answer
from ai_brain.language.tokenizer.trainer import train_tokenizer


def _train_small_tokenizer() -> ByteLevelBpeTokenizer:
    texts = [
        format_prompt_answer(
            "\u0423 \u041c\u0430\u0448\u0438 \u0431\u044b\u043b\u043e 7 \u044f\u0431\u043b\u043e\u043a.",
            "7",
        ),
        format_prompt_answer("Sort 3, 1, 2 from low to high.", "1, 2, 3"),
        format_prompt_answer(
            "\u0415\u0441\u043b\u0438 A > B, \u043a\u0442\u043e \u0431\u043e\u043b\u044c\u0448\u0435?",
            "A",
        ),
    ]
    return ByteLevelBpeTokenizer.train(texts, vocab_size=512, min_frequency=1)


def test_special_token_ids_are_stable() -> None:
    tokenizer = _train_small_tokenizer()

    assert SPECIAL_TOKEN_IDS == {
        token: expected_id for expected_id, token in enumerate(SPECIAL_TOKENS)
    }
    for expected_id, token in enumerate(SPECIAL_TOKENS):
        assert tokenizer.token_to_id(token) == expected_id


def test_prompt_answer_format_is_stable() -> None:
    assert format_prompt_answer("  prompt  ", "  answer  ") == (
        "<|prompt|>\nprompt\n<|answer|>\nanswer\n<|end|>"
    )


def test_encode_decode_roundtrip_keeps_special_tokens() -> None:
    tokenizer = _train_small_tokenizer()
    text = format_prompt_answer(
        "\u0421\u043a\u043e\u043b\u044c\u043a\u043e \u0431\u0443\u0434\u0435\u0442 12 + 5?",
        "17",
    )

    ids = tokenizer.encode(text)

    assert ids
    assert tokenizer.decode(ids, skip_special_tokens=False) == text


def test_rare_unicode_characters_do_not_crash() -> None:
    tokenizer = _train_small_tokenizer()
    text = "Rare symbols: \U0001f9ea \u2603 \u20ac \U0001d11e"

    ids = tokenizer.encode(text)
    decoded = tokenizer.decode(ids, skip_special_tokens=False)

    assert ids
    assert decoded == text


def test_train_tokenizer_from_jsonl_and_save_load(tmp_path) -> None:
    input_path = tmp_path / "dataset.jsonl"
    output_path = tmp_path / "tokenizer.json"
    records = [
        {
            "prompt": "\u0423 \u0410\u043d\u0438 4 \u043a\u043d\u0438\u0433\u0438, \u0430 \u0443 \u041e\u043b\u0438 6. \u0423 \u043a\u043e\u0433\u043e \u0431\u043e\u043b\u044c\u0448\u0435?",
            "answer": "\u0443 \u041e\u043b\u0438",
            "task_type": "quantity.compare",
        },
        {
            "prompt": "Reverse abc.",
            "answer": "cba",
            "task_type": "sequence.reverse",
        },
    ]
    input_path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records),
        encoding="utf-8",
    )

    info = train_tokenizer(
        input_paths=[input_path],
        output_path=output_path,
        vocab_size=512,
        min_frequency=1,
    )
    tokenizer = ByteLevelBpeTokenizer.load(output_path)
    text = format_prompt_answer(records[0]["prompt"], records[0]["answer"])

    assert output_path.exists()
    assert info["type"] == "byte_level_bpe"
    assert info["special_token_ids"] == SPECIAL_TOKEN_IDS
    assert tokenizer.decode(tokenizer.encode(text), skip_special_tokens=False) == text


def test_iter_tokenizer_texts_formats_jsonl_prompt_answer(tmp_path) -> None:
    input_path = tmp_path / "dataset.jsonl"
    input_path.write_text(
        json.dumps({"prompt": "p", "answer": "a"}, ensure_ascii=False),
        encoding="utf-8",
    )

    assert list(iter_tokenizer_texts_from_path(input_path)) == [
        "<|prompt|>\np\n<|answer|>\na\n<|end|>"
    ]
