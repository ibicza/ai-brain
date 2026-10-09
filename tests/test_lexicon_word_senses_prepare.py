"""No spelling-based merging, no false occurrence labels, no training promotions."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "lexical_senses",
    Path(__file__).parents[1] / "scripts/lexicon_word_senses_prepare.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    words = [
        [
            "vc0001",
            "лук",
            "Репчатая луковица как пища.",
            "Еда",
            None,
            "Проверено на синтетике",
            0.8,
            0,
            "user-train",
            "user-test",
            "user-model",
            "user-report",
            "user-note",
            "user-image",
        ]
    ]
    text = [
        [
            "tx1",
            "лук",
            "лук; лука; луком",
            "vc0001",
            3,
            1,
            "ru",
            "candidate",
            "ambiguous",
            "pending",
            "book",
            "context",
            "source",
        ]
    ]
    sense = {
        "lemma": "лук",
        "word": "лук (оружие)",
        "description": "Оружие для стрельбы стрелами с помощью натянутой тетивы.",
        "category": "Предмет",
        "sense_key": "bow",
        "aliases": [],
        "source_text_ids": ["tx1"],
        "example": "Лучник натянул лук.",
        "authored_example": True,
        "scope_note": "Только оружие, не растение.",
        "existing_id": None,
    }
    review = {
        "reviewer": "fixture",
        "training_started": False,
        "training_admitted": False,
        "concepts": [sense],
        "deferred": [],
    }
    return words, text, review


def test_same_spelling_different_sense_gets_new_id_and_preserves_old_fields():
    words, text, review = fixture()
    before = copy.deepcopy(words)
    result, mappings, _ = module.merge_senses(words, text, [review])
    assert result[0] == before[0]
    assert result[1][0] == "vc0002"
    assert result[1][6:12] == [None] * 6
    assert result[1][13] is None
    assert "не цитата" in result[1][12]
    assert mappings[0]["occurrences_disambiguated"] is False


def test_explicit_existing_sense_does_not_duplicate_or_modify_it():
    words, text, review = fixture()
    review["concepts"][0].update(
        existing_id="vc0001",
        sense_key="vegetable",
        word="лук (пищевой)",
        description="Репчатая луковица как пища.",
    )
    result, mappings, _ = module.merge_senses(words, text, [review])
    assert result == words
    assert mappings[0]["concept_id"] == "vc0001"


@pytest.mark.parametrize(
    "field,value",
    [
        ("description", "слово " * 21),
        ("description", ""),
        ("sense_key", ""),
        ("scope_note", ""),
        ("authored_example", False),
        ("source_text_ids", ["unknown"]),
        ("source_text_ids", []),
        ("lemma", "несуществующееслово"),
        ("existing_id", "vc9999"),
    ],
)
def test_refuses_false_or_unscoped_claims(field, value):
    words, text, review = fixture()
    review["concepts"][0][field] = value
    with pytest.raises(ValueError):
        module.merge_senses(words, text, [review])


def test_different_senses_need_visible_qualifiers():
    words, text, review = fixture()
    second = copy.deepcopy(review["concepts"][0])
    second.update(sense_key="another", description="Иное значение.")
    review["concepts"].append(second)
    with pytest.raises(ValueError, match="distinct visible labels"):
        module.merge_senses(words, text, [review])


def test_conflicting_same_sense_key_is_not_silently_merged():
    words, text, review = fixture()
    second = copy.deepcopy(review["concepts"][0])
    second["description"] = "Противоречивое другое определение."
    review["concepts"].append(second)
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        module.merge_senses(words, text, [review])


def test_no_training_allowed():
    words, text, review = fixture()
    review["training_started"] = True
    with pytest.raises(ValueError):
        module.merge_senses(words, text, [review])


def test_existing_id_wrong_meaning_rejected():
    words, text, review = fixture()
    review["concepts"][0]["existing_id"] = "vc0001"
    with pytest.raises(ValueError, match="definition differs"):
        module.merge_senses(words, text, [review])


def test_replay_preserves_sense_id_and_adds_no_duplicate():
    words, text, review = fixture()
    result, mappings, _ = module.merge_senses(words, text, [review])
    replay, replay_mapping, _ = module.merge_senses(result, text, [review], mappings)
    assert replay == result
    assert replay_mapping[0]["concept_id"] == mappings[0]["concept_id"]
    assert replay_mapping[0]["reused_existing_id"] is True


def test_permutations_do_not_reassign_ids():
    words, text, review = fixture()
    second = copy.deepcopy(review)
    second["reviewer"] = "other"
    second["concepts"][0].update(
        sense_key="plant",
        word="лук (растение)",
        description="Огородное растение с луковицей.",
    )
    first, mapping, _ = module.merge_senses(words, text, [review, second])
    other, other_mapping, _ = module.merge_senses(words, text, [second, review])
    assert first == other
    assert mapping == other_mapping


@pytest.mark.parametrize("value", ["=1+1", "+SUM(A1)", "-word", "@value"])
def test_csv_formula_like_text_escaped(value):
    assert module.csv_literal(value) == "'" + value
    assert module.csv_literal(0) == 0


def run_fixture(tmp_path, monkeypatch):
    words, text, review = fixture()
    inc = module.load_increment()
    monkeypatch.setattr(module, "load_increment", lambda: inc)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    source = corpus / "source.txt"
    source.write_text("Лук и стрелы.", encoding="utf-8")
    text[0][12] = str(source)
    media = [
        [
            "source",
            None,
            str(source),
            "Не назначено",
            None,
            None,
            None,
            None,
            None,
            None,
            inc.digest(source),
            None,
            None,
            None,
            None,
            "Нет",
            "PDF_TEXT",
            None,
            None,
        ]
    ]
    values = {
        "words": words,
        "text": text,
        "media": media,
        "coverage": [["book", "sha", 1, 1, 1, 0, 0, "Нет", "draft"]],
    }
    sheets = {
        name: {
            "headers": inc.HEADERS[key],
            "rows": values[key],
            "freeze": True,
            "tables": True,
        }
        for name, key in inc.SHEETS.items()
    }
    monkeypatch.setattr(inc, "saved_tables", lambda _: sheets)
    workbook = tmp_path / "saved.xlsx"
    workbook.write_bytes(b"fixture mocked reader")
    history = {
        **values,
        **{key + "_headers": inc.HEADERS[key] for key in values},
        "review_files": [],
        "training_started": False,
        "training_admitted": False,
        "stats": {"concepts": 1, "media_rows": 1},
    }
    previous = tmp_path / "previous.json"
    previous.write_text(json.dumps(history), encoding="utf-8")
    specification = tmp_path / "senses.json"
    specification.write_text(json.dumps(review), encoding="utf-8")
    output = tmp_path / "qa" / "prepared.json"
    return inc, source, workbook, previous, specification, corpus, output


def test_run_checks_raw_sha_and_preserves_all_saved_sheets(tmp_path, monkeypatch):
    inc, source, wb, previous, specification, corpus, output = run_fixture(
        tmp_path, monkeypatch
    )
    data = module.run(
        wb, previous, [specification], corpus, tmp_path / "reviews", output
    )
    assert data["stats"]["new_word_concepts"] == 1
    assert data["sense_source_files"] == [
        {"path": str(source.resolve()), "sha256": inc.digest(source)}
    ]
    old = json.loads(previous.read_text())
    for key in ("text", "media", "coverage"):
        assert data[key] == old[key]
    assert data["words"][0] == old["words"][0]
    assert data["training_started"] is False


def test_source_hash_mutation_rejected(tmp_path, monkeypatch):
    _, source, wb, previous, specification, corpus, output = run_fixture(
        tmp_path, monkeypatch
    )
    source.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        module.run(wb, previous, [specification], corpus, tmp_path / "reviews", output)


@pytest.mark.parametrize(
    "name", ["prepared.json", "sense_catalogue.json", "word_review_queue.csv"]
)
def test_existing_sidecar_not_overwritten(tmp_path, monkeypatch, name):
    _, _, wb, previous, specification, corpus, output = run_fixture(
        tmp_path, monkeypatch
    )
    output.parent.mkdir()
    old = output.parent / name
    old.write_bytes(b"user saved")
    with pytest.raises(ValueError, match="fresh"):
        module.run(wb, previous, [specification], corpus, tmp_path / "reviews", output)
    assert old.read_bytes() == b"user saved"
