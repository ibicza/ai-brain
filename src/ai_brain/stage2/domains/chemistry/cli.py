"""Command-line interface for the trusted M-28 chemistry domain."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai_brain.stage2.domains.chemistry.formula_parser import FormulaParser
from ai_brain.stage2.domains.chemistry.knowledge_snapshot import atomic_weight_answer
from ai_brain.stage2.domains.chemistry.manifest import (
    build_domain_manifest,
    write_domain_manifest,
)
from ai_brain.stage2.domains.chemistry.rendering import render_tool_output
from ai_brain.stage2.domains.chemistry.replay import replay_chemistry_result
from ai_brain.stage2.domains.chemistry.resolver import resolve_chemistry_element
from ai_brain.stage2.domains.chemistry.service import (
    ChemistryDomainService,
    build_domain,
)
from ai_brain.stage2.domains.chemistry.sources import verify_source_chain
from ai_brain.stage2.domains.chemistry.tool_registry import chemistry_tool_manifests
from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.facts.persistence import FactDatabase

DEFAULT_ROOT = Path("artifacts/domains/chemistry/m281")


def main() -> None:
    parser = argparse.ArgumentParser(prog="ai-brain-chemistry")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build-domain")
    sub.add_parser("verify")
    sub.add_parser("verify-source-chain")
    sub.add_parser("list-elements")
    show = sub.add_parser("show-element")
    show.add_argument("--symbol", required=True)
    weight = sub.add_parser("atomic-weight")
    weight.add_argument("--element", required=True)
    weight.add_argument("--language", choices=("ru", "en"), default="en")
    weight.add_argument(
        "--requested", choices=("STANDARD", "ABRIDGED", "ALL"), default="ALL"
    )
    parse = sub.add_parser("parse-formula")
    parse.add_argument("--formula", required=True)
    _tool_parser(
        sub,
        "molar-mass",
        ("formula", "mode", "unit"),
        {"mode": "conventional", "unit": "g/mol"},
    )
    _tool_parser(sub, "mass-to-moles", ("formula", "value", "unit"), {})
    _tool_parser(sub, "moles-to-mass", ("formula", "value", "unit"), {})
    entities = _tool_parser(sub, "moles-to-entities", ("value",), {})
    entities.add_argument("--formula", required=True)
    entities.add_argument(
        "--basis",
        choices=(
            "FORMULA_ENTITIES",
            "TOTAL_ATOMS_IN_FORMULA",
            "ATOMS_OF_ELEMENT_IN_FORMULA",
        ),
        default="FORMULA_ENTITIES",
    )
    entities.add_argument("--target-element")
    route = sub.add_parser("route-text")
    route.add_argument("--language", choices=("ru", "en"), required=True)
    route.add_argument("--text", required=True)
    provenance = sub.add_parser("provenance")
    provenance.add_argument("--result-hash", required=True)
    backup = sub.add_parser("backup")
    backup.add_argument("--output", type=Path, required=True)
    export = sub.add_parser("export")
    export.add_argument("--output", type=Path, required=True)
    restore = sub.add_parser("restore")
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build-domain":
        _, summary = build_domain(args.root)
        _print(asdict(summary))
        return
    if args.command == "restore":
        target = args.target.resolve()
        FactDatabase.restore(args.backup, target / "fact_memory")
        target.mkdir(parents=True, exist_ok=True)
        source_dir = args.root.resolve() / "sources"
        shutil.copytree(source_dir, target / "sources")
        memory = FactMemory.open(target / "fact_memory")
        tool_hashes = tuple(
            (key, value.manifest_hash)
            for key, value in sorted(chemistry_tool_manifests().items())
        )
        manifest = build_domain_manifest(memory, target / "sources", tool_hashes)
        write_domain_manifest(manifest, target / "domain_manifest.json")
        _print({"status": "RESTORED", "target": str(target)})
        return
    service = ChemistryDomainService.open(args.root)
    if args.command == "verify":
        _print(service.verify())
    elif args.command == "verify-source-chain":
        _print(verify_source_chain(args.root / "sources"))
    elif args.command == "list-elements":
        _print({"elements": service.manifest["supported_elements"]})
    elif args.command == "show-element":
        resolution = resolve_chemistry_element(service.memory, args.symbol, "en")
        if len(resolution.entity_ids) != 1:
            raise ValueError("unknown or case-invalid chemistry element")
        answers = {}
        for predicate in (
            "element_name_en",
            "element_name_ru",
            "atomic_number",
            "conventional_atomic_weight",
        ):
            query = service.memory.make_query(
                subject=resolution.entity_ids[0],
                predicate_id=predicate,
                include_evidence=True,
            )
            answer = service.memory.query(query)
            answers[predicate] = asdict(answer)
        _print(answers)
    elif args.command == "atomic-weight":
        _print(
            asdict(
                atomic_weight_answer(
                    service.memory,
                    service.manifest["domain_manifest_hash"],
                    args.element,
                    language=args.language,
                    requested=args.requested,
                )
            )
        )
    elif args.command == "parse-formula":
        ast = FormulaParser(set(service.manifest["supported_elements"])).parse(
            args.formula
        )
        _print(asdict(ast))
    elif args.command == "route-text":
        decision, response = service.route_text(args.text, args.language)
        _print({"decision": asdict(decision), "response": asdict(response)})
    elif args.command == "provenance":
        result = service.results.load(args.result_hash)
        _print(
            {
                "result": result,
                "replay_status": replay_chemistry_result(
                    result, service.memory, service.manifest
                ),
            }
        )
    elif args.command == "backup":
        _print(service.memory.database.backup(args.output))
    elif args.command == "export":
        _print(service.memory.database.export(args.output))
    else:
        tool_id, arguments = _arguments(args)
        _, prepared, proposal = service.prepare_tool(tool_id, arguments)
        if not args.confirm:
            _print(
                {
                    "status": "PREPARED",
                    "proposal": asdict(proposal),
                    "response": asdict(prepared),
                }
            )
            return
        result, response = service.confirm_and_execute(
            prepared, proposal, identity="chemistry-cli-user"
        )
        if result is None:
            _print({"response": asdict(response)})
        else:
            print(render_tool_output(result.output, args.language))


def _tool_parser(sub, name: str, fields: tuple[str, ...], defaults: dict[str, str]):
    item = sub.add_parser(name)
    for field in fields:
        item.add_argument(
            f"--{field}", required=field not in defaults, default=defaults.get(field)
        )
    item.add_argument("--confirm", action="store_true")
    item.add_argument("--language", choices=("ru", "en"), default="en")
    if name != "moles-to-entities":
        item.add_argument("--significant-digits", type=int, default=6)
    return item


def _arguments(args) -> tuple[str, dict[str, Any]]:
    if args.command == "molar-mass":
        return "chemistry_molar_mass", {
            "formula": args.formula,
            "mode": args.mode,
            "unit": args.unit,
            "significant_digits": args.significant_digits,
        }
    if args.command == "mass-to-moles":
        return "chemistry_mass_amount", {
            "formula": args.formula,
            "value": args.value,
            "source_unit": args.unit,
            "target_unit": "mol",
            "significant_digits": args.significant_digits,
        }
    if args.command == "moles-to-mass":
        return "chemistry_mass_amount", {
            "formula": args.formula,
            "value": args.value,
            "source_unit": "mol",
            "target_unit": args.unit,
            "significant_digits": args.significant_digits,
        }
    return "chemistry_entity_amount", {
        "value": args.value,
        "source_unit": "mol",
        "target_unit": "entities",
        "basis": args.basis,
        "formula": args.formula,
        "target_element": args.target_element,
        "requested_display_label": None,
        "significant_digits": 6,
    }


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
