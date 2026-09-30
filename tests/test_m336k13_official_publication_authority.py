from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k2_publication import (
    _e_source_files,
    _h_source_files,
    build_m336k2_publication_contract,
    publication_contract_from_dict,
)

OFFICIAL_BRANCH = "refs/heads/exp/stage3-m336k13-final-controller-plan-binding-v23"
DISPOSABLE_BRANCH = "refs/heads/disposable/m336k13-r38e-rehearsal-v1"
PUBLICATION_FIELDS = (
    "q_root",
    "f_root",
    "h_root",
    "e_root",
    "q_subject",
    "f_subject",
    "h_subject",
    "e_subject",
)
DISPOSABLE_TUPLE = (
    "artifacts/m336k13/disposable/q38-like",
    "artifacts/m336k13/disposable/f38-like-freeze",
    "artifacts/m336k13/disposable/h38-like",
    "artifacts/m336k13/disposable/e38-like",
    "M-33.6k.13 qualify disposable immutable launch",
    "M-33.6k.13 freeze disposable immutable launch",
    "M-33.6k.13 publish disposable sealed production",
    "M-33.6k.13 publish disposable independent evidence",
)
PUBLICATION_MUTATION_CASES = (
    "official_profile_disposable_roots",
    "official_profile_disposable_subjects",
    "official_profile_hybrid_roots",
    "official_profile_hybrid_subjects",
    "official_tuple_rehearsal_branch",
    "official_tuple_historical_branch",
    "official_branch_case_mutation",
    "official_q_root_changed",
    "official_f_root_changed",
    "official_h_root_changed",
    "official_e_root_changed",
    "official_q_subject_changed",
    "official_f_subject_changed",
    "official_h_subject_changed",
    "official_e_subject_changed",
    "h_e_contract_mismatch",
    "h_exact_e_hybrid",
    "e_exact_h_hybrid",
    "branch_equality_check_omitted",
    "profile_check_omitted",
    "generic_non_null_profile_path_used",
    "official_tuple_added_to_disposable_allowlist",
    "caller_supplied_tuple_accepted",
    "wildcard_task_prefix_accepted",
    "tuple_mismatch_converted_to_warning",
    "route_identity_observation_omitted_from_h",
    "route_identity_observation_omitted_from_e",
    "q38_historical_root_substituted",
    "prospective_f_root_substituted",
    "absolute_root_introduced",
    "traversal_root_introduced",
    "another_task_official_tuple_substituted",
)
HISTORICAL_OFFICIAL = {
    "M336K12_PROFILE_ID": (
        "artifacts/m336k12/q37",
        "artifacts/m336k12/f37-freeze",
        "artifacts/m336k12/h37",
        "artifacts/m336k12/e37",
        "M-33.6k.12 qualify native stage dispatch authority",
        "M-33.6k.12 freeze final Java execution",
        "M-33.6k.12 publish sealed Java production",
        "M-33.6k.12 publish independent Java evidence",
    ),
    "M336K11_PROFILE_ID": (
        "artifacts/m336k11/q36",
        "artifacts/m336k11/f36-freeze",
        "artifacts/m336k11/h36",
        "artifacts/m336k11/e36",
        "M-33.6k.11 qualify hermetic executable authority",
        "M-33.6k.11 freeze final Java execution",
        "M-33.6k.11 publish sealed Java production",
        "M-33.6k.11 publish independent Java evidence",
    ),
    "M336K10_PROFILE_ID": (
        "artifacts/m336k10/q35",
        "artifacts/m336k10/f35-freeze",
        "artifacts/m336k10/h35",
        "artifacts/m336k10/e35",
        "M-33.6k.10 qualify official acquisition authority",
        "M-33.6k.10 freeze final Java execution",
        "M-33.6k.10 publish sealed Java production",
        "M-33.6k.10 publish independent Java evidence",
    ),
}


def _builder():
    scripts = str(Path(__file__).resolve().parents[1] / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import m336k5_build_component_bundle

    return m336k5_build_component_bundle


def _values(branch: str, publication_tuple: tuple[str, ...]) -> dict[str, str]:
    return {
        "branch_ref": branch,
        **dict(zip(PUBLICATION_FIELDS, publication_tuple, strict=True)),
    }


def _seed(
    output: Path,
    publication_tuple: tuple[str, ...],
    branch: str,
    *,
    e_publication_tuple: tuple[str, ...] | None = None,
) -> None:
    contract = build_m336k2_publication_contract(**_values(branch, publication_tuple))
    e_contract = build_m336k2_publication_contract(
        **_values(branch, e_publication_tuple or publication_tuple)
    )
    for name, value in (
        ("h28_publication_contract", contract),
        ("e28_publication_contract", e_contract),
    ):
        (output / f"{name}.json").write_text(
            json.dumps(asdict(value)), encoding="utf-8"
        )
    for name, body in (
        ("implementation_tip", {"exact_implementation_tip": "0" * 40}),
        ("q28_commit", {"exact_q28_sha": "0" * 40}),
        ("commit_protocol", {"branch_ref": "refs/heads/old"}),
    ):
        (output / f"{name}.json").write_text(
            json.dumps({**body, "receipt_hash": content_hash(body)}),
            encoding="utf-8",
        )


def _run(
    output: Path,
    *,
    profile_id: str,
    request_branch: str,
    supplied_tuple: tuple[str, ...] = DISPOSABLE_TUPLE,
    supplied_branch: str = DISPOSABLE_BRANCH,
    e_supplied_tuple: tuple[str, ...] | None = None,
) -> dict[str, str]:
    module = _builder()
    _seed(
        output,
        supplied_tuple,
        supplied_branch,
        e_publication_tuple=e_supplied_tuple,
    )
    module._write_m336k7_legacy_bindings(
        output,
        {
            "identity_namespace": "m336k8",
            "official_profile_id": profile_id,
            "branch_ref": request_branch,
            "exact_implementation_tip": "1" * 40,
            "exact_q30_sha": "2" * 40,
        },
    )
    return json.loads(
        (output / "h28_publication_contract.json").read_text(encoding="utf-8")
    )


def _tuple(value: dict[str, str]) -> tuple[str, ...]:
    return tuple(value[field] for field in PUBLICATION_FIELDS)


def test_exact_official_tuple_is_owned_only_by_m336k13_profile(
    tmp_path: Path,
) -> None:
    module = _builder()
    value = _run(
        tmp_path,
        profile_id=module.M336K13_PROFILE_ID,
        request_branch=OFFICIAL_BRANCH,
    )

    assert _tuple(value) == module.M336K13_OFFICIAL_PUBLICATION_TUPLE
    assert value["branch_ref"] == OFFICIAL_BRANCH
    assert module.M336K13_OFFICIAL_PUBLICATION_TUPLE not in (
        module.M336K_ALLOWED_DISPOSABLE_PUBLICATION_TUPLES
    )


def test_disposable_tuple_remains_accepted_only_for_rehearsal_profile(
    tmp_path: Path,
) -> None:
    value = _run(
        tmp_path,
        profile_id="m336k8-rehearsal-v2",
        request_branch=DISPOSABLE_BRANCH,
    )
    assert _tuple(value) == DISPOSABLE_TUPLE


def test_disposable_tuple_cannot_enter_official_v6_projection(
    tmp_path: Path,
) -> None:
    module = _builder()
    value = _run(
        tmp_path,
        profile_id=module.M336K13_PROFILE_ID,
        request_branch=OFFICIAL_BRANCH,
        supplied_tuple=DISPOSABLE_TUPLE,
    )
    assert _tuple(value) == module.M336K13_OFFICIAL_PUBLICATION_TUPLE
    assert _tuple(value) != DISPOSABLE_TUPLE


def test_official_tuple_is_rejected_by_rehearsal_profile(tmp_path: Path) -> None:
    module = _builder()
    with pytest.raises(
        M336K2ProtocolError, match="M336K9 publication contract changed"
    ):
        _run(
            tmp_path,
            profile_id="m336k8-rehearsal-v2",
            request_branch=DISPOSABLE_BRANCH,
            supplied_tuple=module.M336K13_OFFICIAL_PUBLICATION_TUPLE,
        )


@pytest.mark.parametrize("field_index", range(len(PUBLICATION_FIELDS)))
def test_rehashed_official_value_mutations_cannot_enter_v6_projection(
    tmp_path: Path, field_index: int
) -> None:
    module = _builder()
    mutated = list(module.M336K13_OFFICIAL_PUBLICATION_TUPLE)
    mutated[field_index] += "-mutated"
    value = _run(
        tmp_path,
        profile_id=module.M336K13_PROFILE_ID,
        request_branch=OFFICIAL_BRANCH,
        supplied_tuple=tuple(mutated),
        supplied_branch=OFFICIAL_BRANCH,
    )
    assert _tuple(value) == module.M336K13_OFFICIAL_PUBLICATION_TUPLE
    assert _tuple(value) != tuple(mutated)


@pytest.mark.parametrize(
    "request_branch",
    (
        DISPOSABLE_BRANCH,
        "refs/heads/exp/stage3-m336k13-final-controller-plan-binding-v23-mutated",
        "refs/heads/EXP/stage3-m336k13-final-controller-plan-binding-v23",
        "refs/heads/exp/stage3-m336k12-native-stage-dispatch-v22",
    ),
)
def test_nonofficial_branch_is_not_projected_as_official_branch(
    tmp_path: Path, request_branch: str
) -> None:
    module = _builder()
    value = _run(
        tmp_path,
        profile_id=module.M336K13_PROFILE_ID,
        request_branch=request_branch,
        supplied_tuple=module.M336K13_OFFICIAL_PUBLICATION_TUPLE,
        supplied_branch=OFFICIAL_BRANCH,
    )
    assert value["branch_ref"] == request_branch
    assert value["branch_ref"] != OFFICIAL_BRANCH


@pytest.mark.parametrize("constant_name", tuple(HISTORICAL_OFFICIAL))
def test_historical_explicit_profile_projection_is_unchanged(
    tmp_path: Path, constant_name: str
) -> None:
    module = _builder()
    value = _run(
        tmp_path,
        profile_id=getattr(module, constant_name),
        request_branch=OFFICIAL_BRANCH,
    )
    assert _tuple(value) == HISTORICAL_OFFICIAL[constant_name]


@pytest.mark.parametrize(
    "profile_id",
    (
        "m336k8-final-v7",
        "m336k8-final-v2",
        "m336k9-official-v1",
    ),
)
def test_unknown_or_relabelled_profiles_fail_closed(
    tmp_path: Path, profile_id: str
) -> None:
    with pytest.raises(
        M336K2ProtocolError, match="M336K9 publication contract changed"
    ):
        _run(
            tmp_path,
            profile_id=profile_id,
            request_branch=OFFICIAL_BRANCH,
        )


def test_official_h_and_e_require_route_identity_observation() -> None:
    module = _builder()
    values = _values(OFFICIAL_BRANCH, module.M336K13_OFFICIAL_PUBLICATION_TUPLE)
    contract = build_m336k2_publication_contract(**values)
    assert "route_identity_observation.json" in _h_source_files(contract)
    assert "route_identity_observation.json" in _e_source_files(contract)


def test_official_commit_protocol_projection_is_exact(tmp_path: Path) -> None:
    module = _builder()
    _run(
        tmp_path,
        profile_id=module.M336K13_PROFILE_ID,
        request_branch=OFFICIAL_BRANCH,
    )
    h_contract = publication_contract_from_dict(
        json.loads(
            (tmp_path / "h28_publication_contract.json").read_text(encoding="utf-8")
        )
    )
    e_contract = publication_contract_from_dict(
        json.loads(
            (tmp_path / "e28_publication_contract.json").read_text(encoding="utf-8")
        )
    )
    protocol = json.loads(
        (tmp_path / "commit_protocol.json").read_text(encoding="utf-8")
    )
    expected = _values(OFFICIAL_BRANCH, module.M336K13_OFFICIAL_PUBLICATION_TUPLE)
    assert all(getattr(h_contract, key) == value for key, value in expected.items())
    assert all(getattr(e_contract, key) == value for key, value in expected.items())
    assert protocol["branch_ref"] == OFFICIAL_BRANCH
    assert all(
        protocol[key] == value
        for key, value in expected.items()
        if key.endswith("_subject")
    )


def test_source_guards_keep_official_and_disposable_authorities_separate() -> None:
    module = _builder()
    source = Path(module.__file__).read_text(encoding="utf-8")
    official_offset = source.index(
        'if request.get("official_profile_id") == M336K13_PROFILE_ID:'
    )
    historical_offset = source.index(
        'elif request.get("official_profile_id") == M336K12_PROFILE_ID:'
    )
    generic_offset = source.index(
        'elif request.get("official_profile_id") in '
        "M336K_ALLOWED_DISPOSABLE_PROFILE_IDS:"
    )
    fail_closed_offset = source.index(
        'elif request.get("official_profile_id") is not None:'
    )
    assert official_offset < historical_offset < generic_offset < fail_closed_offset
    assert module.M336K_ALLOWED_DISPOSABLE_PROFILE_IDS == frozenset(
        {"m336k8-rehearsal-v2"}
    )
    assert module.M336K13_OFFICIAL_PUBLICATION_TUPLE not in (
        module.M336K_ALLOWED_DISPOSABLE_PUBLICATION_TUPLES
    )
    assert "startswith(" not in source[official_offset:historical_offset]
    assert "getenv(" not in source[official_offset:historical_offset]


@pytest.mark.parametrize("case", PUBLICATION_MUTATION_CASES)
def test_publication_mutation_matrix_is_closed_under_rehash(
    tmp_path: Path, case: str
) -> None:
    module = _builder()
    official = module.M336K13_OFFICIAL_PUBLICATION_TUPLE
    source = Path(module.__file__).read_text(encoding="utf-8")
    official_block = source.split(
        'if request.get("official_profile_id") == M336K13_PROFILE_ID:', maxsplit=1
    )[1].split(
        'elif request.get("official_profile_id") == M336K12_PROFILE_ID:', maxsplit=1
    )[0]

    if case == "branch_equality_check_omitted":
        assert '"branch_ref": request["branch_ref"]' in official_block
        return
    if case == "profile_check_omitted":
        assert 'request.get("official_profile_id") == M336K13_PROFILE_ID' in source
        return
    if case == "generic_non_null_profile_path_used":
        assert (
            module.M336K13_PROFILE_ID not in module.M336K_ALLOWED_DISPOSABLE_PROFILE_IDS
        )
        return
    if case == "official_tuple_added_to_disposable_allowlist":
        assert official not in module.M336K_ALLOWED_DISPOSABLE_PUBLICATION_TUPLES
        return
    if case == "caller_supplied_tuple_accepted":
        supplied = DISPOSABLE_TUPLE
    elif case == "wildcard_task_prefix_accepted":
        supplied = tuple(value.replace("M-33.6k.13", "M-33.6k.*") for value in official)
    elif case == "tuple_mismatch_converted_to_warning":
        assert (
            'raise M336K2ProtocolError("M336K9 publication contract changed")' in source
        )
        return
    elif case == "route_identity_observation_omitted_from_h":
        contract = build_m336k2_publication_contract(
            **_values(OFFICIAL_BRANCH, official)
        )
        assert "route_identity_observation.json" in _h_source_files(contract)
        return
    elif case == "route_identity_observation_omitted_from_e":
        contract = build_m336k2_publication_contract(
            **_values(OFFICIAL_BRANCH, official)
        )
        assert "route_identity_observation.json" in _e_source_files(contract)
        return
    else:
        supplied_list = list(official)
        replacements = {
            "official_profile_disposable_roots": (*DISPOSABLE_TUPLE[:4], *official[4:]),
            "official_profile_disposable_subjects": (
                *official[:4],
                *DISPOSABLE_TUPLE[4:],
            ),
            "official_profile_hybrid_roots": (*DISPOSABLE_TUPLE[:2], *official[2:]),
            "official_profile_hybrid_subjects": (*official[:6], *DISPOSABLE_TUPLE[6:]),
            "q38_historical_root_substituted": (
                "artifacts/m336k13/q38",
                *official[1:],
            ),
            "prospective_f_root_substituted": (
                official[0],
                "artifacts/m336k13/prospective-f38-freeze",
                *official[2:],
            ),
            "absolute_root_introduced": ("D:/private/q38r", *official[1:]),
            "traversal_root_introduced": ("../q38r", *official[1:]),
            "another_task_official_tuple_substituted": HISTORICAL_OFFICIAL[
                "M336K12_PROFILE_ID"
            ],
        }
        if case in replacements:
            supplied = replacements[case]
        elif case in {
            "official_tuple_rehearsal_branch",
            "official_tuple_historical_branch",
            "official_branch_case_mutation",
            "h_e_contract_mismatch",
            "h_exact_e_hybrid",
            "e_exact_h_hybrid",
        }:
            supplied = official
        else:
            field = case.removeprefix("official_").removesuffix("_changed")
            supplied_list[PUBLICATION_FIELDS.index(field)] += "-mutated"
            supplied = tuple(supplied_list)

    supplied_branch = OFFICIAL_BRANCH
    request_branch = OFFICIAL_BRANCH
    e_supplied = None
    if case == "official_tuple_rehearsal_branch":
        request_branch = DISPOSABLE_BRANCH
    elif case == "official_tuple_historical_branch":
        request_branch = "refs/heads/exp/stage3-m336k12-native-stage-dispatch-v22"
    elif case == "official_branch_case_mutation":
        request_branch = OFFICIAL_BRANCH.upper()
    elif case in {"h_e_contract_mismatch", "h_exact_e_hybrid"}:
        e_supplied = (*official[:4], *DISPOSABLE_TUPLE[4:])
    elif case == "e_exact_h_hybrid":
        supplied = (*official[:4], *DISPOSABLE_TUPLE[4:])
        e_supplied = official

    if case in {"absolute_root_introduced", "traversal_root_introduced"}:
        with pytest.raises(
            M336K2ProtocolError, match="M336K2 publication contract is invalid"
        ):
            _run(
                tmp_path,
                profile_id=module.M336K13_PROFILE_ID,
                request_branch=request_branch,
                supplied_tuple=supplied,
                supplied_branch=supplied_branch,
                e_supplied_tuple=e_supplied,
            )
        return

    value = _run(
        tmp_path,
        profile_id=module.M336K13_PROFILE_ID,
        request_branch=request_branch,
        supplied_tuple=supplied,
        supplied_branch=supplied_branch,
        e_supplied_tuple=e_supplied,
    )
    assert _tuple(value) == official
    if request_branch != OFFICIAL_BRANCH:
        assert value["branch_ref"] != OFFICIAL_BRANCH
