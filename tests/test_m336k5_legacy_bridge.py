from __future__ import annotations

from types import SimpleNamespace

from ai_brain.stage3.acquisition import m336k5_freeze
from ai_brain.stage3.acquisition.m336k2_acquisition import (
    verify_m336k2_final_authorization,
)
from ai_brain.stage3.acquisition.m336k2_protocol import verify_complete_freeze
from ai_brain.stage3.acquisition.m336k2_publication import (
    _e_source_files,
    _h_source_files,
    build_m336k2_publication_contract,
)


def test_legacy_acquisition_dispatches_m336k5_freeze_verifier(
    monkeypatch, tmp_path
) -> None:
    calls = []

    def verify(root, manifest, *, allow_prospective_f30=False):
        calls.append((root, manifest, allow_prospective_f30))

    manifest = SimpleNamespace(contract_role="M336K5_F30_TYPED_FREEZE_V2")
    monkeypatch.setattr(m336k5_freeze, "verify_complete_m336k5_freeze", verify)

    verify_complete_freeze(tmp_path, manifest, allow_prospective_f28=True)

    assert calls == [(tmp_path, manifest, True)]


def test_legacy_acquisition_dispatches_m336k5_authorization_verifier() -> None:
    calls = []

    class Authorization:
        contract_role = "M336K5_TYPED_FINAL_AUTHORIZATION_V2"

        def verify(self) -> None:
            calls.append("verified")

    verify_m336k2_final_authorization(Authorization())

    assert calls == ["verified"]


def test_m336k5_publication_requires_typed_identity_observation() -> None:
    contract = build_m336k2_publication_contract(
        q_root="artifacts/m336k5/q30",
        f_root="artifacts/m336k5/f30-freeze",
        h_root="artifacts/m336k5/h30",
        e_root="artifacts/m336k5/e30",
    )

    assert "route_identity_observation.json" in _h_source_files(contract)
    assert "route_identity_observation.json" in _e_source_files(contract)
