"""M-29.1 acceptance batteries over the trusted educational v2 layer."""

from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path

from ai_brain.stage2.domains.chemistry import replay as chemistry_replay
from ai_brain.stage2.education.exercise_generation import (
    instantiate_variant,
    present_exercise,
    verify_presented_exercise,
)
from ai_brain.stage2.education.explanations import (
    render_explanation,
    verify_explanation,
)
from ai_brain.stage2.education.graph_validation import verify_derivation_graph
from ai_brain.stage2.education.hint_validation import verify_hint_no_answer_leakage
from ai_brain.stage2.education.independent_evaluation import (
    evaluate_independent_fixtures,
)
from ai_brain.stage2.education.models import (
    EducationalDimension,
    EducationalRouteKind,
    ExerciseFamily,
    ExplanationMode,
    GraphNodeKind,
    TutorSessionStatus,
)
from ai_brain.stage2.education.service import verify_educational_route_receipt
from ai_brain.stage2.education.sessions import (
    ALLOWED_EVENT_STATES,
    apply_event,
    make_event,
    start_session,
)
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.facts.models import ClaimStatus, SourceStatus


def run_m291_acceptance(service, fixture_path: Path) -> dict:
    entries = service.catalog.entries
    authority = _authority(service)
    graph = _graph_mutations(entries)
    explanation = _explanation_mutations(entries)
    public = _public_boundary(entries)
    exercises = _exercise_diversity(entries, service.catalog.split_manifests)
    diagnosis = evaluate_independent_fixtures(service.catalog, fixture_path)
    hints = _hint_leakage(entries, diagnosis)
    sessions = _session_matrix(entries[0].internal_instance)
    artifacts = _artifact_semantics(service, entries[0])
    routes = _route_receipts(service)
    imports = _trusted_import_boundary()
    replay = _live_replay(service, entries)
    return {
        "status": "PASS"
        if all(
            (
                authority["runtime_hidden_execution"] == 0,
                graph["accepted_tampered_graphs"] == 0,
                explanation["accepted_unsupported_additions"] == 0,
                public["hidden_answer_leaks"] == 0,
                exercises["distinct_semantic_keys"] >= 2_000,
                diagnosis["wrong_confident_diagnosis"] == 0,
                diagnosis["wrong_targeted_hints"] == 0,
                hints["early_equivalent_answer_leaks"] == 0,
                sessions["invalid_transitions_accepted"] == 0,
                sessions["valid_transitions_rejected"] == 0,
                artifacts["invalid_artifacts_accepted"] == 0,
                routes["tampered_receipts_accepted"] == 0,
                imports["torch_imports"] == 0,
                imports["network_imports"] == 0,
                replay["stale_reported_current"] == 0,
            )
        )
        else "FAIL",
        "authority": authority,
        "graph": graph,
        "explanation": explanation,
        "public_boundary": public,
        "exercises": exercises,
        "diagnosis": diagnosis,
        "hints": hints,
        "sessions": sessions,
        "artifacts": artifacts,
        "controlled_routes": routes,
        "trusted_import_boundary": imports,
        "replay": replay,
        "optional_neural_surface": "DISABLED_NOT_EVALUATED",
        "content_policy_added": False,
    }


def _authority(service):
    before = service.execution_monitor.count
    service.create_exercise(
        ExerciseFamily.MOLAR_MASS_SIMPLE,
        seed=291,
        language="en",
        session_id="m291-authority-presentation",
        created_at="2026-08-28T00:00:00Z",
    )
    presentation = service.execution_monitor.count - before
    before = service.execution_monitor.count
    service.explain_tool(
        "chemistry_molar_mass",
        {
            "formula": "H2O",
            "mode": "conventional",
            "unit": "g/mol",
            "significant_digits": 3,
        },
        language="en",
    )
    precompiled = service.execution_monitor.count - before
    before = service.execution_monitor.count
    _, prepared, proposal = service.explain_tool(
        "chemistry_molar_mass",
        {
            "formula": "O2",
            "mode": "interval",
            "unit": "g/mol",
            "significant_digits": 12,
        },
        language="en",
    )
    unconfirmed = service.execution_monitor.count - before
    before = service.execution_monitor.count
    service.confirm_explanation(
        prepared,
        proposal,
        identity="m291-acceptance-user",
        language="en",
    )
    confirmed = service.execution_monitor.count - before
    return {
        "runtime_hidden_execution": presentation + precompiled + unconfirmed,
        "exercise_presentation_executions": presentation,
        "precompiled_explanation_executions": precompiled,
        "unconfirmed_new_explanation_executions": unconfirmed,
        "unconfirmed_response_stage": prepared.response_stage.value,
        "confirmed_new_explanation_executions": confirmed,
        "offline_compilation_receipt_count": len(service.catalog.entries),
        "offline_compilation_without_receipt": sum(
            not entry.compilation_receipt.receipt_hash
            for entry in service.catalog.entries
        ),
    }


def _graph_mutations(entries):
    categories = (
        "exact_inputs",
        "node_value",
        "unit",
        "dimension",
        "arity",
        "rounding",
        "interval",
        "source_result",
        "provenance",
    )
    accepted = {category: 0 for category in categories}
    cases = {category: 0 for category in categories}
    interval_graphs = [
        entry.graph
        for entry in entries
        if isinstance(_root_node(entry.graph).exact_output, dict)
        and set(_root_node(entry.graph).exact_output) == {"lower", "upper"}
    ]
    unit_graphs = [
        entry.graph for entry in entries if any(node.unit for node in entry.graph.nodes)
    ]
    rounding_graphs = [
        entry.graph
        for entry in entries
        if any(node.kind == GraphNodeKind.ROUND_DISPLAY for node in entry.graph.nodes)
    ]
    for index in range(2_000):
        graph = entries[index % len(entries)].graph
        category = categories[index % len(categories)]
        cases[category] += 1
        if category == "interval":
            graph = interval_graphs[index % len(interval_graphs)]
        elif category in {"unit", "dimension"}:
            graph = unit_graphs[index % len(unit_graphs)]
        elif category == "rounding":
            graph = rounding_graphs[index % len(rounding_graphs)]
        target = next(
            node for node in graph.nodes if node.input_node_ids and node.exact_inputs
        )
        if category == "exact_inputs":
            changed = _rehash_node(
                target, exact_inputs=(*target.exact_inputs[:-1], "m291-tamper")
            )
            tampered = _graph_with_node(graph, changed)
        elif category == "node_value":
            changed = _rehash_node(target, exact_output="291")
            tampered = _graph_with_node(graph, changed)
        elif category == "unit":
            unit_node = next(node for node in graph.nodes if node.unit is not None)
            tampered = _graph_with_node(
                graph, _rehash_node(unit_node, unit="m291-invalid-unit")
            )
        elif category == "dimension":
            dimension_node = next(node for node in graph.nodes if node.unit is not None)
            tampered = _graph_with_node(
                graph,
                _rehash_node(
                    dimension_node, dimension=EducationalDimension.DIMENSIONLESS
                ),
            )
        elif category == "arity":
            changed = _rehash_node(target, input_node_ids=target.input_node_ids[:-1])
            tampered = _graph_with_node(graph, changed)
        elif category == "rounding":
            rounding = next(
                node for node in graph.nodes if node.kind == GraphNodeKind.ROUND_DISPLAY
            )
            tampered = _graph_with_node(
                graph, _rehash_node(rounding, display_output="291")
            )
        elif category == "interval":
            root = next(
                node
                for node in graph.nodes
                if node.node_id == graph.root_result_node_id
            )
            output = {
                "lower": root.exact_output["upper"],
                "upper": root.exact_output["lower"],
            }
            tampered = _graph_with_node(graph, _rehash_node(root, exact_output=output))
        elif category == "source_result":
            artifact = deepcopy(graph.source_result_artifact)
            artifact["m291_tamper"] = True
            tampered = _rehash_graph(graph, source_result_artifact=artifact)
        else:
            tampered = _rehash_graph(graph, source_hashes=("0" * 64,))
        try:
            verify_derivation_graph(tampered)
            accepted[category] += 1
        except (TypeError, ValueError):
            pass
    return {
        "mutation_case_count": 2_000,
        "cases_by_category": cases,
        "accepted_by_category": accepted,
        "accepted_tampered_graphs": sum(accepted.values()),
        "interval_graph_cases": len(interval_graphs),
        "invalid_interval_graphs_accepted": accepted["interval"],
    }


def _explanation_mutations(entries):
    additions = (
        "False unsupported factual sentence.",
        "291",
        "Xe2",
        "291 kg/mol",
        "source: m291-unknown",
        "x = y + 291",
        "Duplicate final answer: 291 mol.",
        "Unicode: ２９１",
        "Equivalent conversion: 0.291 kmol.",
    )
    accepted = {str(index): 0 for index in range(len(additions) + 1)}
    for index in range(1_000):
        graph = entries[index % len(entries)].graph
        artifact = render_explanation(
            graph, language=("ru", "en")[index % 2], mode=ExplanationMode.FULL
        )
        body = asdict(artifact)
        category = index % (len(additions) + 1)
        if category < len(additions):
            body["text"] += "\n" + additions[category]
        else:
            body["plan_hash"] = "0" * 64
        body.pop("explanation_hash")
        tampered = replace(
            artifact,
            text=body["text"],
            plan_hash=body["plan_hash"],
            explanation_hash=content_hash(body),
        )
        try:
            verify_explanation(tampered, graph)
            accepted[str(category)] += 1
        except (TypeError, ValueError):
            pass
    check_leak = 0
    try:
        render_explanation(
            entries[0].graph, language="en", mode=ExplanationMode.CHECK_ONLY
        )
        check_leak = 1
    except ValueError:
        pass
    return {
        "mutation_case_count": 1_000,
        "accepted_by_mutation_category": accepted,
        "accepted_unsupported_additions": sum(accepted.values()),
        "check_only_expected_answer_leaks": check_leak,
    }


def _public_boundary(entries):
    leaks = 0
    for index in range(1_000):
        entry = entries[index % len(entries)]
        instance = instantiate_variant(
            entry.internal_instance,
            entry.exercise_spec,
            entry.graph,
            seed=index,
            language=("ru", "en")[index % 2],
        )
        presented = present_exercise(
            instance, entry.exercise_spec, session_id=f"s{index}"
        )
        verify_presented_exercise(presented)
        fields = set(asdict(presented))
        if fields & {
            "hidden_expected_answer",
            "hidden_answer_graph_hash",
            "counterfactuals",
            "split_axis",
            "compilation_receipt_hash",
        }:
            leaks += 1
    return {
        "serialization_api_cases": 1_000,
        "hidden_answer_leaks": leaks,
        "hidden_graph_leaks": leaks,
        "counterfactual_leaks": leaks,
        "split_label_leaks": leaks,
    }


def _exercise_diversity(entries, split_manifests):
    questions = set()
    semantic = set()
    graph_values = set()
    counts = {}
    for index in range(5_000):
        entry = entries[index % len(entries)]
        instance = instantiate_variant(
            entry.internal_instance,
            entry.exercise_spec,
            entry.graph,
            seed=index,
            language=("ru", "en")[index % 2],
        )
        questions.add(instance.question_text)
        semantic.add(instance.semantic_key_hash)
        graph_values.add(
            (entry.graph.graph_hash, content_hash(instance.hidden_expected_answer))
        )
        counts[instance.semantic_key_hash] = (
            counts.get(instance.semantic_key_hash, 0) + 1
        )
    split_intersections = {
        item["axis"]: item["intersection_count"] for item in split_manifests
    }
    return {
        "presented_instance_count": 5_000,
        "distinct_semantic_keys": len(semantic),
        "distinct_question_strings": len(questions),
        "distinct_graph_value_combinations": len(graph_values),
        "maximum_variants_per_semantic_key": max(counts.values()),
        "fake_holdout_intersections": sum(split_intersections.values()),
    }


def _session_matrix(instance):
    invalid_accepted = 0
    valid_rejected = 0
    cases = 0
    session, _ = start_session(
        instance, session_id="m291-transition", created_at="2026-08-28T00:00:00Z"
    )
    payloads = {
        "ANSWER_SUBMITTED": {"student_answer_hash": "a" * 64},
        "ANSWER_GRADED": {"grading_result_hash": "b" * 64, "solved": False},
        "HINT_ISSUED": {"hint_hash": "c" * 64},
        "SOLUTION_REVEALED": {"explanation_hash": "d" * 64},
        "SESSION_ABANDONED": {},
    }
    for status in TutorSessionStatus:
        attempts = ("e" * 64,) if status != TutorSessionStatus.PRESENTED else ()
        current = _rehash_session(
            session,
            status=status,
            attempt_hashes=attempts,
            grading_result_hashes=(),
            hint_hashes=(),
        )
        for event_type, payload in payloads.items():
            cases += 1
            expected = status in ALLOWED_EVENT_STATES[event_type]
            event = make_event(
                current.session_id,
                sequence=2,
                event_type=event_type,
                payload=payload,
                previous_event_hash=current.last_event_hash,
                created_at="2026-08-28T00:01:00Z",
            )
            try:
                apply_event(current, event)
                if not expected:
                    invalid_accepted += 1
            except ValueError:
                if expected:
                    valid_rejected += 1
    return {
        "transition_cases": cases,
        "invalid_transitions_accepted": invalid_accepted,
        "valid_transitions_rejected": valid_rejected,
    }


def _live_replay(service, entries):
    del entries
    stale_current = 0
    wrong_status = 0
    session_id = "m291-authority-presentation"
    baseline = service.replay(session_id)
    if baseline["status"] != "CURRENT":
        raise ValueError("live replay baseline is not current")
    categories = (
        "domain",
        "fact_memory",
        "source_chain",
        "tool",
        "claim",
        "source",
    )
    expected = {
        "domain": "STALE_DOMAIN",
        "fact_memory": "STALE_FACT_MEMORY",
        "source_chain": "STALE_SOURCE_CHAIN",
        "tool": "STALE_TOOL",
        "claim": "STALE_CLAIM",
        "source": "STALE_SOURCE",
    }
    counts = {category: 0 for category in categories}
    for index in range(100):
        category = categories[index % len(categories)]
        counts[category] += 1
        manifest = service.chemistry.manifest
        memory = service.chemistry.memory
        if category == "domain":
            original = manifest["domain_version"]
            manifest["domain_version"] = "m291-stale-domain"
        elif category == "fact_memory":
            original = manifest["fact_memory_snapshot_hash"]
            manifest["fact_memory_snapshot_hash"] = "0" * 64
        elif category == "source_chain":
            original = manifest["source_chain_hash"]
            manifest["source_chain_hash"] = "0" * 64
        elif category == "tool":
            original = chemistry_replay.CHEMISTRY_CALCULATION_POLICY_VERSION
            chemistry_replay.CHEMISTRY_CALCULATION_POLICY_VERSION = "m291-stale"
        elif category == "claim":
            original = memory.get_claim_state

            def stale_claim(claim_id, _original=original):
                return replace(_original(claim_id), status=ClaimStatus.RETRACTED)

            memory.get_claim_state = stale_claim
        else:
            original = memory.get_source_state

            def stale_source(source_id, _original=original):
                return replace(_original(source_id), status=SourceStatus.RETRACTED)

            memory.get_source_state = stale_source
        try:
            result = service.replay(session_id)
        finally:
            if category == "domain":
                manifest["domain_version"] = original
            elif category == "fact_memory":
                manifest["fact_memory_snapshot_hash"] = original
            elif category == "source_chain":
                manifest["source_chain_hash"] = original
            elif category == "tool":
                chemistry_replay.CHEMISTRY_CALCULATION_POLICY_VERSION = original
            elif category == "claim":
                memory.get_claim_state = original
            else:
                memory.get_source_state = original
        if result["status"] == "CURRENT":
            stale_current += 1
        if result["status"] != expected[category]:
            wrong_status += 1
    return {
        "live_mutation_cases": 100,
        "cases_by_category": counts,
        "stale_reported_current": stale_current,
        "wrong_stale_reason": wrong_status,
        "baseline_status": baseline["status"],
    }


def _hint_leakage(entries, diagnosis):
    accepted = 0
    for index in range(100):
        graph = entries[index % len(entries)].graph
        root = next(
            node for node in graph.nodes if node.node_id == graph.root_result_node_id
        )
        if isinstance(root.exact_output, dict):
            if set(root.exact_output) == {"lower", "upper"}:
                text = f"{root.exact_output['lower']}, {root.exact_output['upper']}"
            else:
                text = " ".join(
                    f"{key}:{value}"
                    for key, value in reversed(root.exact_output.items())
                )
        else:
            text = f"{root.exact_output} {root.unit or ''}"
        try:
            verify_hint_no_answer_leakage(text, root)
            accepted += 1
        except ValueError:
            pass
    return {
        "strong_equivalence_cases": 100,
        "early_equivalent_answer_leaks": accepted,
        "independently_tested_targeted_hints": diagnosis[
            "independently_tested_targeted_hints"
        ],
        "wrong_targeted_hints": diagnosis["wrong_targeted_hints"],
    }


def _artifact_semantics(service, entry):
    accepted = 0
    cases = 0
    semantically_invalid = _rehash_graph(entry.graph, source_hashes=("0" * 64,))
    for kind, key, artifact in (
        ("unknown_m291_kind", entry.graph.graph_hash, entry.graph),
        ("derivation_graph", "0" * 64, entry.graph),
        (
            "derivation_graph",
            semantically_invalid.graph_hash,
            semantically_invalid,
        ),
    ):
        cases += 1
        try:
            service.store.save_artifact(kind, key, artifact)
            accepted += 1
        except (KeyError, TypeError, ValueError):
            pass
    service.store.verify()
    return {
        "semantic_rejection_cases": cases,
        "invalid_artifacts_accepted": accepted,
        "full_store_verification": "VERIFIED",
    }


def _route_receipts(service):
    _, receipt, result = service.handle_controlled(
        "Give me a molar-mass exercise.", language="en", seed=292
    )
    verify_educational_route_receipt(receipt)
    if receipt.session_id != result[1].session_id:
        raise ValueError("controlled route receipt lost its generated session")
    accepted = 0
    for changes in (
        {"route_kind": EducationalRouteKind.HINT},
        {"session_id": "m291-wrong-session"},
    ):
        try:
            verify_educational_route_receipt(replace(receipt, **changes))
            accepted += 1
        except ValueError:
            pass
    return {"tamper_cases": 2, "tampered_receipts_accepted": accepted}


def _trusted_import_boundary():
    education = Path(__file__).resolve().parent
    chemistry_education = education.parent / "domains" / "chemistry" / "education"
    sources = tuple(education.glob("*.py")) + tuple(chemistry_education.glob("*.py"))
    torch_imports = 0
    network_imports = 0
    for source in sources:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            modules = ()
            if isinstance(node, ast.Import):
                modules = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = (node.module,)
            for module in modules:
                root = module.split(".", 1)[0]
                torch_imports += root == "torch"
                network_imports += root in {
                    "requests",
                    "httpx",
                    "urllib",
                    "socket",
                    "aiohttp",
                }
    return {
        "scanned_python_files": len(sources),
        "torch_imports": torch_imports,
        "network_imports": network_imports,
    }


def _rehash_node(node, **changes):
    body = asdict(node)
    body.update(changes)
    body.pop("node_hash")
    return replace(node, **changes, node_hash=content_hash(body))


def _root_node(graph):
    return next(
        node for node in graph.nodes if node.node_id == graph.root_result_node_id
    )


def _graph_with_node(graph, changed):
    nodes = tuple(
        changed if node.node_id == changed.node_id else node for node in graph.nodes
    )
    return _rehash_graph(graph, nodes=nodes)


def _rehash_graph(graph, **changes):
    body = asdict(graph)
    body.update(changes)
    body.pop("graph_hash")
    return replace(graph, **changes, graph_hash=content_hash(body))


def _rehash_session(session, **changes):
    body = asdict(session)
    body.update(changes)
    body.pop("session_hash")
    return replace(session, **changes, session_hash=content_hash(body))
