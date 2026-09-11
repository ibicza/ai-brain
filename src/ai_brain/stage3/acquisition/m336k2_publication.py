"""Native H28/E28 publication and commit protocol for M-33.6k.2."""

from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336g_publication import (
    verify_java_public_candidate_pack,
)
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2_BRANCH_REF,
    M336K2_E28_SUBJECT,
    M336K2_F28_SUBJECT,
    M336K2_H28_SUBJECT,
    M336K2_Q28_SUBJECT,
    M336K2ProtocolError,
    m336k2_minimal_environment,
)

M336K2_H28_ROOT = Path("artifacts/m336k2/h28-production")
M336K2_E28_ROOT = Path("artifacts/m336k2/e28-evidence")

_H_ROOT_FILES = frozenset(
    {
        "field_evidence_manifest.json",
        "public_pack_integrity_receipt.json",
        "sealed_source_replay_receipt.json",
        "windows_production_seal.json",
        "karina_production_seal.json",
        "production_comparison.json",
        "public_staging_manifest.json",
        "public_staging_receipt.json",
    }
)
_E_SOURCE_FILES = frozenset(
    {
        "windows_evaluation.json",
        "karina_evaluation.json",
        "evaluation_comparison.json",
        "runtime_receipt.json",
        "final_route_ledger_receipt.json",
        "source_leak_report.json",
    }
)
_FORBIDDEN_SUFFIXES = frozenset(
    {".java", ".class", ".jar", ".zip", ".tar", ".gz", ".tgz", ".7z"}
)
_ABSOLUTE_PATH = re.compile(
    rb"(?:(?<![A-Za-z0-9+.-])[A-Za-z]:[\\/]"
    rb"|\\\\[^\\\s]+[\\/]"
    rb"|/(?:home|Users|tmp|var|opt)/)"
)
_JAVA_WINDOW = re.compile(
    rb"(?:package\s+[A-Za-z_]|import\s+[A-Za-z_]|(?:public|private|protected)\s+(?:class|interface|enum|record)\s+)"
)


@dataclass(frozen=True)
class M336K2PublicationReport:
    schema_version: int
    contract_role: str
    exact_parent_sha: str
    output_tree_hash: str
    output_file_count: int
    candidate_pack_content_hash: str | None
    candidate_pack_tree_hash: str | None
    source_leak_count: int
    absolute_path_count: int
    private_artifact_count: int
    uncontracted_artifact_count: int
    status: str
    report_hash: str


@dataclass(frozen=True)
class M336K2PublicationContract:
    schema_version: int
    contract_role: str
    branch_ref: str
    q_root: str
    f_root: str
    h_root: str
    e_root: str
    q_subject: str
    f_subject: str
    h_subject: str
    e_subject: str
    contract_hash: str


def build_m336k2_publication_contract(
    *,
    branch_ref: str = M336K2_BRANCH_REF,
    q_root: str = "artifacts/m336k2/q28",
    f_root: str = "artifacts/m336k2/f28-freeze",
    h_root: str = M336K2_H28_ROOT.as_posix(),
    e_root: str = M336K2_E28_ROOT.as_posix(),
    q_subject: str = M336K2_Q28_SUBJECT,
    f_subject: str = M336K2_F28_SUBJECT,
    h_subject: str = M336K2_H28_SUBJECT,
    e_subject: str = M336K2_E28_SUBJECT,
) -> M336K2PublicationContract:
    body = {
        "schema_version": 1,
        "contract_role": "M336K2_NATIVE_H28_E28_PUBLICATION_CONTRACT",
        "branch_ref": branch_ref,
        "q_root": q_root,
        "f_root": f_root,
        "h_root": h_root,
        "e_root": e_root,
        "q_subject": q_subject,
        "f_subject": f_subject,
        "h_subject": h_subject,
        "e_subject": e_subject,
    }
    result = M336K2PublicationContract(**body, contract_hash=content_hash(body))
    verify_m336k2_publication_contract(result)
    return result


def publication_contract_from_dict(value: dict) -> M336K2PublicationContract:
    if set(value) != set(M336K2PublicationContract.__dataclass_fields__):
        raise M336K2ProtocolError("M336K2 publication contract fields changed")
    result = M336K2PublicationContract(**value)
    verify_m336k2_publication_contract(result)
    return result


def verify_m336k2_publication_contract(
    contract: M336K2PublicationContract,
) -> None:
    body = asdict(contract)
    claimed = body.pop("contract_hash")
    roots = (contract.q_root, contract.f_root, contract.h_root, contract.e_root)
    if (
        contract.schema_version != 1
        or contract.contract_role != "M336K2_NATIVE_H28_E28_PUBLICATION_CONTRACT"
        or not contract.branch_ref.startswith("refs/heads/")
        or any(not _safe_public_root(item) for item in roots)
        or len(set(roots)) != len(roots)
        or any(
            not isinstance(item, str) or not item.strip()
            for item in (
                contract.q_subject,
                contract.f_subject,
                contract.h_subject,
                contract.e_subject,
            )
        )
        or content_hash(body) != claimed
    ):
        raise M336K2ProtocolError("M336K2 publication contract is invalid")


def stage_m336k2_h28_publication(
    *,
    repository: Path,
    git_executable: Path,
    exact_f28_sha: str,
    production_source: Path,
    output: Path,
    contract: M336K2PublicationContract | None = None,
) -> M336K2PublicationReport:
    """Stage only the contracted source-free production subset."""

    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    contract = contract or build_m336k2_publication_contract()
    verify_m336k2_publication_contract(contract)
    source = production_source.resolve(strict=True)
    destination = output.resolve(strict=False)
    expected = (root / contract.h_root).resolve(strict=False)
    _verify_clean_pushed_head(root, git, exact_f28_sha, contract.branch_ref)
    if destination != expected or destination.exists() or source.is_relative_to(root):
        raise M336K2ProtocolError("M336K2 H28 publication paths are invalid")
    source_names = {item.name for item in source.iterdir()}
    expected_names = _H_ROOT_FILES | {"candidate_pack"}
    missing = expected_names - source_names
    if missing:
        raise M336K2ProtocolError(
            f"M336K2 H28 production source is incomplete: {len(missing)} missing"
        )
    destination.mkdir(parents=True)
    shutil.copytree(source / "candidate_pack", destination / "candidate_pack")
    for name in sorted(_H_ROOT_FILES):
        shutil.copyfile(source / name, destination / name)
    pack = verify_java_public_candidate_pack(destination / "candidate_pack")
    safety = scan_m336k2_public_tree(destination, allowed_root_files=expected_names)
    if any(safety.values()):
        raise M336K2ProtocolError("M336K2 H28 public-safety contract failed")
    return _write_report(
        destination,
        name="h28_publication_report.json",
        role="PUBLIC_SAFE_M336K2_H28_PRODUCTION_REPORT",
        parent=exact_f28_sha,
        pack_content=pack.candidate_pack_content_hash,
        pack_tree=pack.candidate_pack_tree_hash,
    )


def stage_m336k2_e28_publication(
    *,
    repository: Path,
    git_executable: Path,
    exact_f28_sha: str,
    exact_h28_sha: str,
    evidence_source: Path,
    output: Path,
    contract: M336K2PublicationContract | None = None,
) -> M336K2PublicationReport:
    """Stage source-free evaluation evidence without changing the H28 pack."""

    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    contract = contract or build_m336k2_publication_contract()
    verify_m336k2_publication_contract(contract)
    source = evidence_source.resolve(strict=True)
    destination = output.resolve(strict=False)
    expected = (root / contract.e_root).resolve(strict=False)
    _verify_clean_pushed_head(root, git, exact_h28_sha, contract.branch_ref)
    if _git(git, root, "rev-parse", f"{exact_h28_sha}^") != exact_f28_sha:
        raise M336K2ProtocolError("M336K2 E28 requires H28 parent to be exact F28")
    if destination != expected or destination.exists() or source.is_relative_to(root):
        raise M336K2ProtocolError("M336K2 E28 publication paths are invalid")
    source_names = {item.name for item in source.iterdir() if item.is_file()}
    if source_names != _E_SOURCE_FILES or any(
        item.is_dir() for item in source.iterdir()
    ):
        raise M336K2ProtocolError("M336K2 E28 evidence source contract changed")
    h_pack = root / contract.h_root / "candidate_pack"
    before = verify_java_public_candidate_pack(h_pack)
    destination.mkdir(parents=True)
    for name in sorted(_E_SOURCE_FILES):
        _load_public_json(source / name)
        shutil.copyfile(source / name, destination / name)
    safety = scan_m336k2_public_tree(destination, allowed_root_files=_E_SOURCE_FILES)
    after = verify_java_public_candidate_pack(h_pack)
    if before != after:
        raise M336K2ProtocolError("M336K2 E28 changed the H28 candidate pack")
    if any(safety.values()):
        raise M336K2ProtocolError("M336K2 E28 public-safety contract failed")
    return _write_report(
        destination,
        name="e28_publication_report.json",
        role="PUBLIC_SAFE_M336K2_E28_EVIDENCE_REPORT",
        parent=exact_h28_sha,
        pack_content=before.candidate_pack_content_hash,
        pack_tree=before.candidate_pack_tree_hash,
    )


def verify_m336k2_commit_protocol(
    *,
    repository: Path,
    git_executable: Path,
    exact_q28_sha: str,
    exact_f28_sha: str,
    exact_h28_sha: str,
    exact_e28_sha: str,
    contract: M336K2PublicationContract | None = None,
) -> dict:
    """Verify exact Q/F/H/E topology, subjects, allowlists, and immutability."""

    root = repository.resolve(strict=True)
    git = git_executable.resolve(strict=True)
    contract = contract or build_m336k2_publication_contract()
    verify_m336k2_publication_contract(contract)
    h_root = Path(contract.h_root)
    e_root = Path(contract.e_root)
    _verify_clean_pushed_head(root, git, exact_e28_sha, contract.branch_ref)
    parents = (
        _git(git, root, "rev-parse", f"{exact_f28_sha}^"),
        _git(git, root, "rev-parse", f"{exact_h28_sha}^"),
        _git(git, root, "rev-parse", f"{exact_e28_sha}^"),
    )
    subjects = tuple(
        _git(git, root, "show", "-s", "--format=%s", sha)
        for sha in (exact_q28_sha, exact_f28_sha, exact_h28_sha, exact_e28_sha)
    )
    h_paths = _diff_paths(git, root, exact_f28_sha, exact_h28_sha)
    e_paths = _diff_paths(git, root, exact_h28_sha, exact_e28_sha)
    q_paths = _diff_paths(git, root, f"{exact_q28_sha}^", exact_q28_sha)
    f_paths = _diff_paths(git, root, exact_q28_sha, exact_f28_sha)
    unauthorized_q = tuple(
        path
        for path in q_paths
        if not (
            path.startswith((contract.q_root + "/", "runs/m336k2/q28/"))
            or (path.startswith("docs/m336k2_") and path.casefold().endswith(".md"))
        )
    )
    unauthorized_f = tuple(
        path for path in f_paths if not path.startswith(contract.f_root + "/")
    )
    unauthorized_h = tuple(
        path for path in h_paths if not path.startswith(h_root.as_posix() + "/")
    )
    unauthorized_e = tuple(
        path for path in e_paths if not path.startswith(e_root.as_posix() + "/")
    )
    implementation_changes = tuple(
        path
        for path in _diff_paths(git, root, exact_f28_sha, exact_e28_sha)
        if path.startswith(("src/", "scripts/", "tools/", "tests/", "schemas/"))
    )
    h_pack_changes = tuple(
        path
        for path in e_paths
        if path.startswith((h_root / "candidate_pack").as_posix() + "/")
    )
    merges = int(
        _git(
            git,
            root,
            "rev-list",
            "--count",
            "--merges",
            f"{exact_q28_sha}..{exact_e28_sha}",
        )
    )
    h_safety = scan_m336k2_public_tree(
        root / h_root,
        allowed_root_files=_H_ROOT_FILES
        | {"candidate_pack", "h28_publication_report.json"},
    )
    e_safety = scan_m336k2_public_tree(
        root / e_root,
        allowed_root_files=_E_SOURCE_FILES | {"e28_publication_report.json"},
    )
    q_safety = scan_m336k2_public_tree(
        root / contract.q_root,
        allowed_root_files=frozenset(
            item.name for item in (root / contract.q_root).iterdir()
        ),
    )
    f_safety = scan_m336k2_public_tree(
        root / contract.f_root,
        allowed_root_files=frozenset(
            item.name for item in (root / contract.f_root).iterdir()
        ),
    )
    expected_h_names = _H_ROOT_FILES | {
        "candidate_pack",
        "h28_publication_report.json",
    }
    expected_e_names = _E_SOURCE_FILES | {"e28_publication_report.json"}
    actual_h_names = {item.name for item in (root / h_root).iterdir()}
    actual_e_names = {item.name for item in (root / e_root).iterdir()}
    pack = verify_java_public_candidate_pack(root / h_root / "candidate_pack")
    h_report = _verified_publication_report(
        root / h_root,
        "h28_publication_report.json",
        expected_parent=exact_f28_sha,
    )
    e_report = _verified_publication_report(
        root / e_root,
        "e28_publication_report.json",
        expected_parent=exact_h28_sha,
    )
    reports_match_pack = all(
        report["candidate_pack_content_hash"] == pack.candidate_pack_content_hash
        and report["candidate_pack_tree_hash"] == pack.candidate_pack_tree_hash
        for report in (h_report, e_report)
    )
    passed = (
        parents == (exact_q28_sha, exact_f28_sha, exact_h28_sha)
        and subjects
        == (
            contract.q_subject,
            contract.f_subject,
            contract.h_subject,
            contract.e_subject,
        )
        and not unauthorized_q
        and not unauthorized_f
        and not unauthorized_h
        and not unauthorized_e
        and not implementation_changes
        and not h_pack_changes
        and not merges
        and actual_h_names == expected_h_names
        and actual_e_names == expected_e_names
        and reports_match_pack
        and not any(q_safety.values())
        and not any(f_safety.values())
        and not any(h_safety.values())
        and not any(e_safety.values())
    )
    body = {
        "schema_version": 1,
        "contract_role": "M336K2_Q28_F28_H28_E28_COMMIT_PROTOCOL_RECEIPT",
        "exact_q28_sha": exact_q28_sha,
        "exact_f28_sha": exact_f28_sha,
        "exact_h28_sha": exact_h28_sha,
        "exact_e28_sha": exact_e28_sha,
        "parents": parents,
        "subjects": subjects,
        "merge_count": merges,
        "unauthorized_q_path_count": len(unauthorized_q),
        "unauthorized_f_path_count": len(unauthorized_f),
        "unauthorized_h_path_count": len(unauthorized_h),
        "unauthorized_e_path_count": len(unauthorized_e),
        "post_f28_implementation_change_count": len(implementation_changes),
        "h_pack_change_during_e_count": len(h_pack_changes),
        "source_leak_count": sum(
            item["source_leak_count"]
            for item in (q_safety, f_safety, h_safety, e_safety)
        ),
        "absolute_path_count": sum(
            item["absolute_path_count"]
            for item in (q_safety, f_safety, h_safety, e_safety)
        ),
        "private_artifact_count": sum(
            item["private_artifact_count"]
            for item in (q_safety, f_safety, h_safety, e_safety)
        ),
        "status": "PASS" if passed else "FAIL",
    }
    result = {**body, "receipt_hash": content_hash(body)}
    if not passed:
        raise M336K2ProtocolError("M336K2 Q/F/H/E commit protocol failed")
    return result


def scan_m336k2_public_tree(root: Path, *, allowed_root_files: frozenset[str]) -> dict:
    source_leaks = 0
    absolute_paths = 0
    private_artifacts = 0
    uncontracted = 0
    if not root.is_dir():
        raise M336K2ProtocolError("M336K2 public tree is missing")
    for entry in root.iterdir():
        if entry.name not in allowed_root_files:
            uncontracted += 1
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        lowered = relative.casefold()
        raw = path.read_bytes()
        if path.suffix.casefold() in _FORBIDDEN_SUFFIXES or _JAVA_WINDOW.search(raw):
            source_leaks += 1
        if _ABSOLUTE_PATH.search(raw):
            absolute_paths += 1
        if any(
            token in lowered
            for token in ("private", "golden", "oracle", "source-archive")
        ):
            private_artifacts += 1
        if _contains_reversible_java_encoding(raw):
            source_leaks += 1
    return {
        "source_leak_count": source_leaks,
        "absolute_path_count": absolute_paths,
        "private_artifact_count": private_artifacts,
        "uncontracted_artifact_count": uncontracted,
    }


def _contains_reversible_java_encoding(raw: bytes) -> bool:
    for match in re.finditer(rb"[A-Za-z0-9+/]{344,}={0,2}", raw):
        try:
            decoded = base64.b64decode(match.group(), validate=True)
        except ValueError:
            continue
        if len(decoded) >= 256 and _JAVA_WINDOW.search(decoded):
            return True
    for match in re.finditer(rb"[0-9a-fA-F]{512,}", raw):
        try:
            decoded = bytes.fromhex(match.group().decode("ascii"))
        except ValueError:
            continue
        if _JAVA_WINDOW.search(decoded):
            return True
    return False


def _write_report(
    root: Path,
    *,
    name: str,
    role: str,
    parent: str,
    pack_content: str | None,
    pack_tree: str | None,
) -> M336K2PublicationReport:
    rows = _rows(root)
    safety = scan_m336k2_public_tree(
        root, allowed_root_files=frozenset(item[0].split("/")[0] for item in rows)
    )
    body = {
        "schema_version": 1,
        "contract_role": role,
        "exact_parent_sha": parent,
        "output_tree_hash": content_hash(rows),
        "output_file_count": len(rows),
        "candidate_pack_content_hash": pack_content,
        "candidate_pack_tree_hash": pack_tree,
        **safety,
        "status": "PASS" if not any(safety.values()) else "FAIL",
    }
    report = M336K2PublicationReport(**body, report_hash=content_hash(body))
    if report.status != "PASS":
        raise M336K2ProtocolError("M336K2 publication report failed")
    (root / name).write_text(
        canonical_json(asdict(report)) + "\n", encoding="utf-8", newline="\n"
    )
    return report


def _load_public_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K2 public evidence is not JSON") from error
    if not isinstance(value, dict):
        raise M336K2ProtocolError("M336K2 public evidence is not an object")
    return value


def _verified_publication_report(
    root: Path, name: str, *, expected_parent: str
) -> dict:
    value = _load_public_json(root / name)
    body = dict(value)
    claimed = body.pop("report_hash", None)
    rows = tuple(row for row in _rows(root) if row[0] != name)
    if (
        not isinstance(claimed, str)
        or content_hash(body) != claimed
        or value.get("exact_parent_sha") != expected_parent
        or value.get("output_tree_hash") != content_hash(rows)
        or value.get("output_file_count") != len(rows)
        or value.get("status") != "PASS"
    ):
        raise M336K2ProtocolError("M336K2 publication report is invalid")
    return value


def _rows(root: Path) -> tuple[tuple[str, int, str], ...]:
    return tuple(
        (
            path.relative_to(root).as_posix(),
            path.stat().st_size,
            bytes_hash(path.read_bytes()),
        )
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(root).as_posix().encode("utf-8"),
        )
    )


def _verify_clean_pushed_head(
    root: Path, git: Path, expected: str, branch_ref: str
) -> None:
    head = _git(git, root, "rev-parse", "HEAD^{commit}")
    upstream = _git(git, root, "rev-parse", "@{upstream}^{commit}")
    remote = _git(git, root, "ls-remote", "--exit-code", "origin", branch_ref)
    remote_sha = remote.split()[0] if remote else ""
    if (
        head != expected
        or upstream != expected
        or remote_sha != expected
        or _git(git, root, "status", "--porcelain=v1")
    ):
        raise M336K2ProtocolError("M336K2 publication requires a clean pushed head")


def _diff_paths(git: Path, root: Path, left: str, right: str) -> tuple[str, ...]:
    return tuple(
        line
        for line in _git(git, root, "diff", "--name-only", left, right).splitlines()
        if line
    )


def _git(git: Path, root: Path, *arguments: str) -> str:
    return subprocess.run(
        (str(git), *arguments),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=m336k2_minimal_environment(),
    ).stdout.strip()


def _safe_public_root(value: str) -> bool:
    path = Path(value)
    return (
        value == path.as_posix()
        and not path.is_absolute()
        and value not in {"", "."}
        and ".." not in path.parts
        and "\\" not in value
        and path.parts[0] == "artifacts"
    )
