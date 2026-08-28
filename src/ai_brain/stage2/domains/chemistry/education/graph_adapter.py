"""Narrow educational access to verified chemistry facts and exact tools."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ai_brain.stage2.domains.chemistry.formula_parser import FormulaParser
from ai_brain.stage2.domains.chemistry.knowledge_snapshot import (
    atomic_weight_answer,
    validate_fact_provenance,
)
from ai_brain.stage2.domains.chemistry.resolver import resolve_chemistry_element
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.education.graph import make_edge, make_graph, make_node
from ai_brain.stage2.education.graph_builder import build_fact_graph, build_result_graph
from ai_brain.stage2.education.graph_validation import verify_derivation_graph
from ai_brain.stage2.education.models import (
    EducationalDerivationGraph,
    GraphEdgeKind,
    GraphNodeKind,
)
from ai_brain.stage2.facts.canonical import canonical_json, content_hash

EDUCATIONAL_TOOL_IDS = frozenset(
    {
        "chemistry_formula_composition",
        "chemistry_molar_mass",
        "chemistry_mass_amount",
        "chemistry_entity_amount",
    }
)


class ChemistryEducationAdapter:
    def __init__(self, service: ChemistryDomainService) -> None:
        self.service = service
        self.parser = FormulaParser(set(service.manifest["supported_elements"]))

    def tool_graph(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        *,
        created_at: str | None = None,
        request_hash: str | None = None,
    ) -> tuple[dict[str, Any], EducationalDerivationGraph]:
        raise PermissionError(
            "runtime educational code cannot execute chemistry tools; use a "
            "precompiled catalog or a completed confirmed result"
        )

    def graph_from_completed_result(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        *,
        created_at: str | None = None,
        request_hash: str | None = None,
        route_decision_hash: str | None = None,
    ) -> EducationalDerivationGraph:
        """Build a graph from an already-authorized immutable result."""
        if tool_id not in EDUCATIONAL_TOOL_IDS:
            raise ValueError("educational adapter only permits chemistry exact tools")
        manifest_hash = self.service.registry.descriptor(
            tool_id
        ).implementation_manifest_hash
        if result.get("tool_implementation_manifest_hash") not in {
            None,
            manifest_hash,
        }:
            raise ValueError("completed chemistry result uses another tool build")
        graph = build_result_graph(
            result,
            tool_implementation_hash=manifest_hash,
            request_hash=request_hash,
            route_decision_hash=route_decision_hash,
            created_at=created_at,
        )
        self.verify_graph(graph, result)
        return graph

    def fact_graph(
        self,
        symbol: str,
        predicate_id: str,
        *,
        language: str,
        created_at: str | None = None,
    ) -> tuple[dict[str, Any], EducationalDerivationGraph]:
        resolution = resolve_chemistry_element(self.service.memory, symbol, language)
        if len(resolution.entity_ids) != 1:
            raise ValueError("unknown or ambiguous chemistry element")
        subject = resolution.entity_ids[0]
        if predicate_id in {
            "standard_atomic_weight",
            "conventional_atomic_weight",
        }:
            request = "STANDARD" if predicate_id.startswith("standard") else "ABRIDGED"
            raw = asdict(
                atomic_weight_answer(
                    self.service.memory,
                    self.service.manifest,
                    symbol,
                    language=language,
                    requested=request,
                )
            )
            if (
                predicate_id == "standard_atomic_weight"
                and raw["standard_kind"] == "INTERVAL"
            ):
                value: Any = {
                    "lower": raw["standard_interval_lower"],
                    "upper": raw["standard_interval_upper"],
                }
            else:
                value = (
                    raw["standard_nominal"]
                    if predicate_id == "standard_atomic_weight"
                    else raw["abridged_value"]
                )
            answer = raw
            binding_predicates = (predicate_id,)
            if (
                predicate_id == "standard_atomic_weight"
                and raw["standard_kind"] == "INTERVAL"
            ):
                binding_predicates = (
                    "standard_atomic_weight_lower",
                    "standard_atomic_weight_upper",
                )
            bindings = tuple(
                validate_fact_provenance(
                    self.service.memory, self.service.manifest, subject, predicate
                )
                for predicate in binding_predicates
            )
            answer["claim_ids"] = tuple(binding.claim_id for binding in bindings)
        else:
            validate_fact_provenance(
                self.service.memory, self.service.manifest, subject, predicate_id
            )
            query = self.service.memory.make_query(
                subject=subject, predicate_id=predicate_id, include_evidence=True
            )
            queried = asdict(self.service.memory.query(query))
            if len(queried["claims"]) != 1:
                raise ValueError("fact query is not an exact single answer")
            claim = queried["claims"][0]
            value = claim["value"]["value"]
            answer = {
                "fact_memory_snapshot_hash": self.service.manifest[
                    "fact_memory_snapshot_hash"
                ],
                "claim_ids": (claim["claim_id"],),
                "evidence_hashes": tuple(claim["supporting_evidence_hashes"]),
                "source_record_hashes": tuple(claim["supporting_source_hashes"]),
                "derivation_hashes": tuple(
                    self.service.manifest["source_derivation_hashes"]
                ),
                "value": value,
                "predicate_id": predicate_id,
            }
            answer["answer_hash"] = content_hash(answer)
        answer["answer_hash"] = content_hash(
            {key: value for key, value in answer.items() if key != "answer_hash"}
        )
        graph = build_fact_graph(
            answer,
            domain_version=self.service.manifest["domain_version"],
            domain_manifest_hash=self.service.manifest["domain_manifest_hash"],
            source_chain_version=self.service.manifest["source_chain_version"],
            source_chain_hash=self.service.manifest["source_chain_hash"],
            field_name=predicate_id,
            value=value,
            unit="u" if "atomic_weight" in predicate_id else None,
            request_hash=content_hash(
                {"symbol": symbol, "predicate_id": predicate_id, "language": language}
            ),
            created_at=created_at,
        )
        self.verify_graph(graph)
        return answer, graph

    def verify_graph(
        self,
        graph: EducationalDerivationGraph,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        verification = verify_derivation_graph(
            graph, expected_source_result=result if result is not None else None
        )
        if graph.domain_version != self.service.manifest["domain_version"]:
            raise ValueError("educational graph has a stale chemistry domain")
        if graph.source_chain_hash != self.service.manifest["source_chain_hash"]:
            raise ValueError("educational graph has a stale source chain")
        for node in graph.nodes:
            if node.kind == GraphNodeKind.FORMULA_PARSE:
                ast = self.parser.parse(str(node.exact_output))
                expected = node.metadata["composition"]
                actual = {item.symbol: item.count for item in ast.composition}
                if (
                    actual != expected
                    or ast.ast_hash != node.metadata["formula_ast_hash"]
                ):
                    raise ValueError("educational graph formula AST mismatch")
        if graph.tool_implementation_hash is not None:
            matching = {
                value for _, value in self.service.registry.current_manifest_hashes()
            }
            if graph.tool_implementation_hash not in matching:
                raise ValueError("educational graph has a stale chemistry tool")
        return verification

    def paired_fact_graph(
        self,
        symbol: str,
        given_predicate: str,
        answer_predicate: str,
        *,
        language: str,
        created_at: str,
    ) -> tuple[Any, Any, EducationalDerivationGraph]:
        given_answer, given_graph = self.fact_graph(
            symbol, given_predicate, language=language, created_at=created_at
        )
        answer, answer_graph = self.fact_graph(
            symbol, answer_predicate, language=language, created_at=created_at
        )
        given_source = next(
            node for node in given_graph.nodes if node.kind == GraphNodeKind.FACT_LOOKUP
        )
        answer_source = next(
            node
            for node in answer_graph.nodes
            if node.kind == GraphNodeKind.FACT_LOOKUP
        )
        given = make_node(
            "given",
            GraphNodeKind.FACT_LOOKUP,
            given_predicate,
            exact_output=given_source.exact_output,
            unit=given_source.unit,
            dimension=given_source.dimension,
            claim_ids=given_source.claim_ids,
            evidence_hashes=given_source.evidence_hashes,
            source_hashes=given_source.source_hashes,
            derivation_hashes=given_source.derivation_hashes,
            metadata={"predicate_id": given_predicate, "role": "question_given"},
        )
        expected = make_node(
            "answer",
            GraphNodeKind.FACT_LOOKUP,
            answer_predicate,
            exact_output=answer_source.exact_output,
            unit=answer_source.unit,
            dimension=answer_source.dimension,
            claim_ids=answer_source.claim_ids,
            evidence_hashes=answer_source.evidence_hashes,
            source_hashes=answer_source.source_hashes,
            derivation_hashes=answer_source.derivation_hashes,
            metadata={"predicate_id": answer_predicate, "role": "answer_key"},
        )
        final = make_node(
            "final",
            GraphNodeKind.FINAL_RESULT,
            "paired fact answer",
            operation="IDENTITY",
            input_node_ids=("answer",),
            exact_inputs=(
                canonical_json(expected.exact_output)
                if isinstance(expected.exact_output, dict)
                else str(expected.exact_output),
            ),
            exact_output=expected.exact_output,
            unit=expected.unit,
            dimension=expected.dimension,
            display_output=str(expected.exact_output),
        )
        source_hashes = tuple(sorted(set(given.source_hashes + expected.source_hashes)))
        source_nodes = tuple(
            make_node(
                f"s{index}",
                GraphNodeKind.SOURCE_REFERENCE,
                "verified source",
                exact_output=source_hash,
                source_hashes=(source_hash,),
                metadata={"source_hash": source_hash},
            )
            for index, source_hash in enumerate(source_hashes, start=1)
        )
        source_result_hash = content_hash(
            {
                "given_result_hash": given_graph.source_result_hash,
                "answer_result_hash": answer_graph.source_result_hash,
            }
        )
        graph = make_graph(
            graph_id=f"education.graph.{source_result_hash[:24]}",
            domain_id="chemistry",
            domain_version=self.service.manifest["domain_version"],
            source_result_type="ChemistryPairedFactAnswer",
            source_result_hash=source_result_hash,
            source_result_artifact={
                "given": given_answer,
                "answer": answer,
                "given_result_hash": given_graph.source_result_hash,
                "answer_result_hash": answer_graph.source_result_hash,
            },
            request_hash=content_hash(
                {
                    "symbol": symbol,
                    "given_predicate": given_predicate,
                    "answer_predicate": answer_predicate,
                    "language": language,
                }
            ),
            route_decision_hash=None,
            fact_memory_snapshot_hash=self.service.manifest[
                "fact_memory_snapshot_hash"
            ],
            knowledge_snapshot_hash=content_hash(
                {
                    "given_graph": given_graph.graph_hash,
                    "answer_graph": answer_graph.graph_hash,
                }
            ),
            formula_ast_hash=None,
            tool_implementation_hash=None,
            calculation_policy_version="FACT_LOOKUP",
            rounding_policy_hash=content_hash("NO_ROUNDING"),
            source_chain_version=self.service.manifest["source_chain_version"],
            source_chain_hash=self.service.manifest["source_chain_hash"],
            nodes=(given, expected, final, *source_nodes),
            edges=(
                make_edge("answer", "final", GraphEdgeKind.SUPPORTS_RESULT),
                make_edge("given", "final", GraphEdgeKind.DEPENDS_ON),
                *(
                    make_edge(node.node_id, "given", GraphEdgeKind.CITES_SOURCE)
                    for node in source_nodes
                    if node.exact_output in given.source_hashes
                ),
                *(
                    make_edge(node.node_id, "answer", GraphEdgeKind.CITES_SOURCE)
                    for node in source_nodes
                    if node.exact_output in expected.source_hashes
                ),
            ),
            root_result_node_id="final",
            claim_ids=tuple(sorted(set(given.claim_ids + expected.claim_ids))),
            evidence_hashes=tuple(
                sorted(set(given.evidence_hashes + expected.evidence_hashes))
            ),
            source_hashes=source_hashes,
            derivation_hashes=tuple(
                sorted(set(given.derivation_hashes + expected.derivation_hashes))
            ),
            created_at=created_at,
        )
        self.verify_graph(graph)
        return given_answer, answer, graph
