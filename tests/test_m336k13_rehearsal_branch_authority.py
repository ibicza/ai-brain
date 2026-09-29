from __future__ import annotations

import inspect
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k9_authorization import (
    M336K9FinalAuthorization,
)
from ai_brain.stage3.acquisition.m336k9_profiles import (
    M336KOfficialRouteProfileRegistry,
    M336KOfficialRouteProfileStatus,
    m336k_official_profile_registry,
)
from ai_brain.stage3.acquisition.m336k13_rehearsal import (
    M336K13_BRANCH_AUTHORITY_MUTATION_CASES,
    M336K13RehearsalBranchAuthorityReceipt,
    build_m336k13_pre_reservation_authorization_projection,
    verify_m336k_rehearsal_branch_authority,
)

_REHEARSAL_PROFILE = "m336k8-rehearsal-v2"
_REHEARSAL_BRANCH = "disposable/m336k8-profile-rehearsal-v2"
_WRONG_REHEARSAL_BRANCH = "disposable/m336k8-m336k13-r38e-full-rehearsal-v3"
_OFFICIAL_PROFILE = "m336k8-final-v6"
_OFFICIAL_BRANCH = "exp/stage3-m336k13-final-controller-plan-binding-v23"


def _verify(
    branch: str,
    *,
    profile_id: str | None = _REHEARSAL_PROFILE,
    official: bool = False,
    namespace: str = "m336k8",
    registry: M336KOfficialRouteProfileRegistry | None = None,
):
    return verify_m336k_rehearsal_branch_authority(
        namespace=namespace,
        disposable_branch=branch,
        official_admission_only=official,
        profile_id=profile_id,
        registry=registry,
    )


@pytest.mark.parametrize(
    ("case", "branch", "profile_id", "official", "namespace", "accepted"),
    (
        (
            "exact-rehearsal",
            _REHEARSAL_BRANCH,
            _REHEARSAL_PROFILE,
            False,
            "m336k8",
            True,
        ),
        (
            "prefix-compatible-wrong",
            _WRONG_REHEARSAL_BRANCH,
            _REHEARSAL_PROFILE,
            False,
            "m336k8",
            False,
        ),
        (
            "suffix",
            f"{_REHEARSAL_BRANCH}-extra",
            _REHEARSAL_PROFILE,
            False,
            "m336k8",
            False,
        ),
        (
            "case",
            "Disposable/m336k8-profile-rehearsal-v2",
            _REHEARSAL_PROFILE,
            False,
            "m336k8",
            False,
        ),
        (
            "double-slash",
            "disposable//m336k8-profile-rehearsal-v2",
            _REHEARSAL_PROFILE,
            False,
            "m336k8",
            False,
        ),
        (
            "trailing-slash",
            f"{_REHEARSAL_BRANCH}/",
            _REHEARSAL_PROFILE,
            False,
            "m336k8",
            False,
        ),
        (
            "official-in-rehearsal",
            _OFFICIAL_BRANCH,
            _OFFICIAL_PROFILE,
            False,
            "m336k8",
            False,
        ),
        (
            "rehearsal-in-official",
            _REHEARSAL_BRANCH,
            _REHEARSAL_PROFILE,
            True,
            "m336k8",
            False,
        ),
        ("exact-official", _OFFICIAL_BRANCH, _OFFICIAL_PROFILE, True, "m336k8", True),
        (
            "historical",
            "exp/stage3-m336k12-native-stage-dispatch-v21",
            "m336k8-final-v5",
            True,
            "m336k8",
            False,
        ),
        (
            "unknown",
            _REHEARSAL_BRANCH,
            "m336k8-rehearsal-unknown",
            False,
            "m336k8",
            False,
        ),
        ("missing-official-profile", _OFFICIAL_BRANCH, None, True, "m336k8", False),
        (
            "profileless-generic",
            "disposable/m336k8-generic-v1",
            None,
            False,
            "m336k8",
            True,
        ),
        (
            "profileless-wrong-namespace",
            "disposable/m336k7-generic-v1",
            None,
            False,
            "m336k8",
            False,
        ),
        (
            "embedded-ref-prefix",
            f"refs/heads/{_REHEARSAL_BRANCH}",
            _REHEARSAL_PROFILE,
            False,
            "m336k8",
            False,
        ),
        (
            "leading-whitespace",
            f" {_REHEARSAL_BRANCH}",
            _REHEARSAL_PROFILE,
            False,
            "m336k8",
            False,
        ),
        (
            "unicode-confusable",
            "disposable/m336k8-prоfile-rehearsal-v2",
            _REHEARSAL_PROFILE,
            False,
            "m336k8",
            False,
        ),
        (
            "control-character",
            f"{_REHEARSAL_BRANCH}\x00",
            _REHEARSAL_PROFILE,
            False,
            "m336k8",
            False,
        ),
    ),
)
def test_m336k13_direct_branch_authority_matrix(
    case: str,
    branch: str,
    profile_id: str | None,
    official: bool,
    namespace: str,
    accepted: bool,
) -> None:
    del case
    if accepted:
        decision = _verify(
            branch,
            profile_id=profile_id,
            official=official,
            namespace=namespace,
        )
        assert decision.mode_status_match is True
    else:
        with pytest.raises(
            M336K2ProtocolError, match="M336K9 route branch authority changed"
        ):
            _verify(
                branch,
                profile_id=profile_id,
                official=official,
                namespace=namespace,
            )


def _forged_registry() -> M336KOfficialRouteProfileRegistry:
    registry = m336k_official_profile_registry()
    original = registry.profile(_REHEARSAL_PROFILE)
    body = {
        **original._body(),
        "authorization_branch_ref": f"refs/heads/{_WRONG_REHEARSAL_BRANCH}",
    }
    forged_profile = replace(
        original,
        authorization_branch_ref=body["authorization_branch_ref"],
        profile_hash=content_hash(body),
    )
    return M336KOfficialRouteProfileRegistry.build(
        tuple(
            forged_profile if profile.profile_id == _REHEARSAL_PROFILE else profile
            for profile in registry.profiles
        )
    )


def test_m336k13_fully_rehashed_registry_profile_forgery_is_rejected() -> None:
    forged = _forged_registry()
    forged.verify()
    with pytest.raises(
        M336K2ProtocolError, match="M336K9 route branch authority changed"
    ):
        _verify(_WRONG_REHEARSAL_BRANCH, registry=forged)


def test_m336k13_fully_rehashed_pass_receipt_forgery_is_rejected() -> None:
    receipt = M336K13RehearsalBranchAuthorityReceipt.build(_verify(_REHEARSAL_BRANCH))
    changed = replace(receipt, branch_exact_match=False, receipt_hash="0" * 64)
    forged = replace(changed, receipt_hash=content_hash(changed._body()))
    with pytest.raises(
        M336K2ProtocolError, match="M336K13 branch authority receipt is invalid"
    ):
        forged.verify()

    changed = replace(receipt, profile_hash="f" * 64, receipt_hash="0" * 64)
    forged_profile = replace(changed, receipt_hash=content_hash(changed._body()))
    with pytest.raises(
        M336K2ProtocolError, match="M336K13 branch authority receipt is invalid"
    ):
        forged_profile.verify()


def _capture_projected_authorization(monkeypatch: pytest.MonkeyPatch):
    captured = {}
    original = M336K9FinalAuthorization.verify

    def capture(self, bundle=None):
        original(self, bundle)
        captured["authorization"] = self
        captured["bundle"] = bundle

    monkeypatch.setattr(M336K9FinalAuthorization, "verify", capture)
    report = build_m336k13_pre_reservation_authorization_projection(
        exact_implementation_tip="1" * 40,
        disposable_label="m336k13-active-v6-plan-rehearsal-r38f-v4",
        namespace="m336k8",
        disposable_branch=_REHEARSAL_BRANCH,
        profile_id=_REHEARSAL_PROFILE,
    )
    assert report["status"] == "PASS"
    assert report["base_predicate_failure_count"] == 0
    assert report["bundle_mismatch_count"] == 0
    return captured["authorization"], captured["bundle"]


def test_m336k13_typed_authorization_branch_parity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization, bundle = _capture_projected_authorization(monkeypatch)
    assert authorization.branch_ref == f"refs/heads/{_REHEARSAL_BRANCH}"
    changed = replace(
        authorization,
        branch_ref=f"refs/heads/{_WRONG_REHEARSAL_BRANCH}",
        authorization_hash="0" * 64,
    )
    forged = replace(changed, authorization_hash=content_hash(changed._body()))
    with pytest.raises(
        M336K2ProtocolError, match="M336K5 typed final authorization is invalid"
    ):
        forged.verify(bundle)


def _qualifier_module():
    scripts = str(Path(__file__).resolve().parents[1] / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import m336k5_qualify_disposable_protocol

    return m336k5_qualify_disposable_protocol


def _preflight_module():
    scripts = str(Path(__file__).resolve().parents[1] / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import m336k13_preflight_disposable_request

    return m336k13_preflight_disposable_request


def test_m336k13_external_preflight_writes_matching_fresh_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "base_sha": "1" * 40,
                "protocol_namespace": "m336k8",
                "official_profile_id": _REHEARSAL_PROFILE,
                "disposable_branch": _REHEARSAL_BRANCH,
                "disposable_label": "m336k13-active-v6-plan-rehearsal-r38f-v4",
            }
        ),
        encoding="utf-8",
    )
    receipt_outputs = [
        tmp_path / "artifacts-receipt.json",
        tmp_path / "runs-receipt.json",
    ]
    projection_outputs = [
        tmp_path / "artifacts-projection.json",
        tmp_path / "runs-projection.json",
    ]
    argv = ["preflight", "--request", str(request)]
    for output in receipt_outputs:
        argv.extend(("--receipt-output", str(output)))
    for output in projection_outputs:
        argv.extend(("--projection-output", str(output)))
    monkeypatch.setattr(sys, "argv", argv)
    _preflight_module().main()
    capsys.readouterr()
    receipt_values = [
        json.loads(path.read_text(encoding="utf-8")) for path in receipt_outputs
    ]
    projection_values = [
        json.loads(path.read_text(encoding="utf-8")) for path in projection_outputs
    ]
    assert receipt_values[0] == receipt_values[1]
    assert projection_values[0] == projection_values[1]
    M336K13RehearsalBranchAuthorityReceipt.from_dict(receipt_values[0])
    assert projection_values[0]["status"] == "PASS"
    assert projection_values[0]["base_predicate_failure_count"] == 0
    assert projection_values[0]["bundle_mismatch_count"] == 0


def _invalid_qualifier_request(output: Path) -> dict:
    values = {
        name: "unused"
        for name in (
            "source_repository",
            "git_executable",
            "python_executable",
            "legacy_component_request_template",
            "stage_request_template",
            "powershell_executable",
            "resource_budget_policy",
            "resource_observation",
            "resource_gate",
            "capsule_binding_set",
            "legacy_capsule_compatibility",
            "persistent_private_capsule",
            "persistent_public_capsule_receipt",
            "legacy_public_capsule_receipt",
            "persistent_python_environment_manifest",
            "capsule_content_manifest",
            "capsule_lifecycle_policy",
            "capsule_liveness",
            "preservation_set",
            "cleanup_plan",
            "cleanup_cutoff_state",
            "candidate_pool",
            "storage_reservation",
            "storage_reservation_file",
            "persistent_karina_overlay",
        )
    }
    return {
        **values,
        "base_sha": "0" * 40,
        "disposable_branch": _WRONG_REHEARSAL_BRANCH,
        "disposable_label": "m336k13-invalid-branch-test",
        "output": str(output),
        "protocol_namespace": "m336k8",
        "official_profile_id": _REHEARSAL_PROFILE,
        "native_stage_dispatch_generation": "m336k12",
        "final_controller_plan_generation": "m336k13",
    }


def test_m336k13_qualifier_rejects_wrong_branch_before_all_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "must-not-exist"
    request = tmp_path / "request.json"
    request.write_text(json.dumps(_invalid_qualifier_request(output)), encoding="utf-8")
    module = _qualifier_module()
    monkeypatch.setattr(
        sys,
        "argv",
        ["qualifier", "--request", str(request), "--startup-receipt", "unused"],
    )
    monkeypatch.setattr(
        module, "_git", lambda *args, **kwargs: pytest.fail("Git invoked")
    )
    with pytest.raises(
        M336K2ProtocolError, match="M336K9 route branch authority changed"
    ):
        module.main()
    assert not output.exists()


def _qualifier_order_is_safe(source: str) -> bool:
    gate = source.find("branch_authority = verify_m336k_rehearsal_branch_authority(")
    boundaries = (
        source.find("output.mkdir(parents=True)"),
        source.find("monitor = M336K5ResourceMonitor("),
        source.find('remote = output / "origin.git"'),
        source.find("q_like = _commit("),
        source.find("typed_request = {"),
    )
    return gate >= 0 and all(boundary > gate for boundary in boundaries)


@pytest.mark.parametrize("case", M336K13_BRANCH_AUTHORITY_MUTATION_CASES)
def test_m336k13_closed_under_rehash_branch_authority_mutations(
    case: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    envelope_body = {
        "contract_role": "M336K13_BRANCH_AUTHORITY_MUTATION",
        "case": case,
        "expected_semantic_layer": "BRANCH_AUTHORITY",
    }
    envelope = {**envelope_body, "receipt_hash": content_hash(envelope_body)}
    assert envelope["receipt_hash"] == content_hash(envelope_body)

    qualifier_source = inspect.getsource(_qualifier_module())
    if case == "early-gate-omitted":
        changed = qualifier_source.replace(
            "branch_authority = verify_m336k_rehearsal_branch_authority(",
            "branch_authority = omitted_branch_authority_gate(",
            1,
        )
        assert not _qualifier_order_is_safe(changed)
        return
    if case in {
        "early-gate-after-output-creation",
        "early-gate-after-q-like-commit",
        "q-like-commit-before-branch-parity-proof",
    }:
        gate = "branch_authority = verify_m336k_rehearsal_branch_authority("
        changed = qualifier_source.replace(gate, "branch_authority = delayed_gate(", 1)
        assert not _qualifier_order_is_safe(changed)
        return
    if case == "registry-lookup-omitted":
        assert "canonical_registry.profile(profile_id)" in inspect.getsource(
            verify_m336k_rehearsal_branch_authority
        )
        return
    if case in {
        "rehashed-profile-branch-canonical-registry-unchanged",
        "rehashed-changed-registry",
        "caller-supplied-profile-bypasses-registry",
    }:
        with pytest.raises(M336K2ProtocolError, match="route branch authority"):
            _verify(_WRONG_REHEARSAL_BRANCH, registry=_forged_registry())
        return
    if case == "branch-receipt-forged-pass":
        receipt = M336K13RehearsalBranchAuthorityReceipt.build(
            _verify(_REHEARSAL_BRANCH)
        )
        changed = replace(receipt, branch_exact_match=False, receipt_hash="0" * 64)
        forged = replace(changed, receipt_hash=content_hash(changed._body()))
        with pytest.raises(M336K2ProtocolError, match="receipt is invalid"):
            forged.verify()
        return
    if case in {
        "exact-identity-forged-authorization-branch",
        "typed-request-branch-changed-after-preflight",
        "typed-authorization-branch-differs-from-preflight",
    }:
        authorization, bundle = _capture_projected_authorization(monkeypatch)
        changed = replace(
            authorization,
            branch_ref=f"refs/heads/{_WRONG_REHEARSAL_BRANCH}",
            authorization_hash="0" * 64,
        )
        forged = replace(changed, authorization_hash=content_hash(changed._body()))
        with pytest.raises(M336K2ProtocolError, match="typed final authorization"):
            forged.verify(bundle)
        return
    if case in {
        "exact-branch-wrong-profile",
        "unknown-profile-relabelled-rehearsal",
    }:
        with pytest.raises(M336K2ProtocolError, match="route branch authority"):
            _verify(_REHEARSAL_BRANCH, profile_id="m336k8-rehearsal-unknown")
        return
    if case == "historical-profile-relabelled-rehearsal":
        with pytest.raises(M336K2ProtocolError, match="route branch authority"):
            _verify(
                "exp/stage3-m336k12-native-stage-dispatch-v21",
                profile_id="m336k8-final-v5",
                official=True,
            )
        return
    if case in {
        "exact-profile-branch-wrong-mode",
        "official-profile-relabelled-rehearsal",
    }:
        with pytest.raises(M336K2ProtocolError, match="route branch authority"):
            _verify(_OFFICIAL_BRANCH, profile_id=_OFFICIAL_PROFILE)
        return
    branch = {
        "branch-prefix-only": "disposable/m336k8-",
        "branch-suffix": f"{_REHEARSAL_BRANCH}-extra",
        "branch-case": "Disposable/m336k8-profile-rehearsal-v2",
        "branch-double-slash": "disposable//m336k8-profile-rehearsal-v2",
        "branch-trailing-slash": f"{_REHEARSAL_BRANCH}/",
        "branch-encoded-separator": "disposable%2fm336k8-profile-rehearsal-v2",
        "branch-whitespace": f"{_REHEARSAL_BRANCH} ",
        "case-insensitive-branch-equality": "Disposable/m336k8-profile-rehearsal-v2",
    }.get(case, _WRONG_REHEARSAL_BRANCH)
    if case == "caller-supplied-expected-branch":
        assert (
            "expected_branch"
            not in inspect.signature(verify_m336k_rehearsal_branch_authority).parameters
        )
    with pytest.raises(M336K2ProtocolError, match="route branch authority"):
        _verify(branch)


def test_m336k13_branch_authority_mutation_suite_is_complete() -> None:
    assert len(M336K13_BRANCH_AUTHORITY_MUTATION_CASES) == 30
    assert len(set(M336K13_BRANCH_AUTHORITY_MUTATION_CASES)) == 30
    source = inspect.getsource(_qualifier_module())
    assert _qualifier_order_is_safe(source)
    assert source.count("verify_m336k_rehearsal_branch_authority(") == 1
    assert 'startswith(f"disposable/{namespace}-")' not in source


def test_m336k13_rehearsal_profile_status_is_unchanged() -> None:
    profile = m336k_official_profile_registry().profile(_REHEARSAL_PROFILE)
    assert profile.profile_status is M336KOfficialRouteProfileStatus.REHEARSAL_ONLY
    assert profile.authorization_branch_ref == f"refs/heads/{_REHEARSAL_BRANCH}"
