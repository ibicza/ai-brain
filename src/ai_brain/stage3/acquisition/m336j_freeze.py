"""F25 authorization and freeze identities for M-33.6j."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336i_acquisition import (
    M336IFinalAcquisitionAuthorization,
    verify_m336i_final_acquisition_authorization,
)

M336J_EXACT_F24_SHA = "4891de1c3a0f6ba2d5d012ab5189dbb5222ba6bd"
M336J_EXACT_Q23_SHA = "067855a9c3dfdfd503011444f08896d867beceac"
M336J_BRANCH_REF = "refs/heads/exp/stage3-m336j-hermetic-karina-final-java-v9"
M336J_ACQUISITION_RUN_ID = "m336j.final-java.global-acquisition.v1"
M336J_FREEZE_ROOT = Path("artifacts/acquisition/m336j_freeze_v9")
M336J_FROZEN_AUTHORIZATION_PATH = (
    M336J_FREEZE_ROOT / "final_acquisition_authorization.json"
)
M336J_FREEZE_MANIFEST_PATH = M336J_FREEZE_ROOT / "freeze_manifest.json"
M336J_FREEZE_IDENTITY_EXCLUSIONS = frozenset(
    {
        M336J_FROZEN_AUTHORIZATION_PATH.as_posix(),
        M336J_FREEZE_MANIFEST_PATH.as_posix(),
    }
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def build_m336j_final_acquisition_authorization(
    **values,
) -> M336IFinalAcquisitionAuthorization:
    body = {
        "schema_version": 1,
        "authorization_role": "FROZEN_FINAL_ACQUISITION_AUTHORIZATION",
        **values,
    }
    authorization = M336IFinalAcquisitionAuthorization(
        **body, authorization_hash=content_hash(body)
    )
    verify_m336j_final_acquisition_authorization(authorization)
    return authorization


def m336j_final_acquisition_authorization_from_dict(
    value: dict,
) -> M336IFinalAcquisitionAuthorization:
    if not isinstance(value, dict) or set(value) != set(
        M336IFinalAcquisitionAuthorization.__dataclass_fields__
    ):
        raise ValueError("M336J final acquisition authorization fields changed")
    authorization = M336IFinalAcquisitionAuthorization(
        **{**value, "allowed_network_hosts": tuple(value["allowed_network_hosts"])}
    )
    verify_m336j_final_acquisition_authorization(authorization)
    return authorization


def verify_m336j_final_acquisition_authorization(
    authorization: M336IFinalAcquisitionAuthorization,
) -> None:
    verify_m336i_final_acquisition_authorization(authorization)
    if (
        authorization.acquisition_mode != "FINAL"
        or authorization.exact_q23_sha != M336J_EXACT_Q23_SHA
        or authorization.acquisition_run_id != M336J_ACQUISITION_RUN_ID
        or authorization.branch_ref != M336J_BRANCH_REF
        or any(
            _SHA256.fullmatch(getattr(authorization, name)) is None
            for name in (
                "r24_implementation_tree_identity",
                "q24_evidence_identity",
                "f24_freeze_tree_identity",
            )
        )
    ):
        raise ValueError("M336J final acquisition authorization is invalid")


def compute_m336j_freeze_tree_identity(repository: Path) -> str:
    root = repository.resolve(strict=True)
    raw = _git(
        root,
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
        binary=True,
    )
    explicit = {
        path.relative_to(root).as_posix()
        for path in (root / M336J_FREEZE_ROOT).rglob("*")
        if path.is_file()
    }
    paths = tuple(
        sorted(
            {
                item.decode("utf-8", errors="strict")
                for item in raw.split(b"\0")
                if item
                and item.decode("utf-8", errors="strict")
                not in M336J_FREEZE_IDENTITY_EXCLUSIONS
            }
            | (explicit - M336J_FREEZE_IDENTITY_EXCLUSIONS),
            key=lambda item: item.encode("utf-8"),
        )
    )
    return content_hash(
        tuple((path, bytes_hash((root / path).read_bytes())) for path in paths)
    )


def _git(repository: Path, *arguments: str, binary: bool = False):
    result = subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
    )
    return result.stdout if binary else result.stdout.decode().strip()
