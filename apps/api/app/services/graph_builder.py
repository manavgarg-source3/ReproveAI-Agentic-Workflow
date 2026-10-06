"""Deterministic projection of persisted REPROVE records into a graph snapshot."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from app.schemas.graph import EdgeType, GraphEdge, GraphNode, GraphSnapshot, NodeType
from app.schemas.investigation import DiagnosticPlan


def generate_id(node_type: str, entity_id: str) -> str:
    return f"{node_type}_{entity_id}"


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _entity_id(entity: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = entity.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def build_graph(research_case_id: str, analyze_response: dict[str, Any], db: Any) -> GraphSnapshot:
    """Project persisted entities and only explicitly recorded relationships."""

    created_at = datetime.now(timezone.utc)
    nodes: dict[str, GraphNode] = {}
    pending_edges: dict[str, GraphEdge] = {}

    def add_node(
        node_type: NodeType,
        entity_id: str,
        label: str,
        source_table: str,
        metadata: dict[str, Any] | None = None,
    ) -> GraphNode:
        node_id = generate_id(node_type.value, entity_id)
        source_metadata = metadata or {}
        node = GraphNode(
            id=node_id,
            node_type=node_type,
            entity_id=entity_id,
            label=label,
            source_table=source_table,
            created_at=created_at,
            source_hash=_hash(source_metadata),
            metadata=source_metadata,
        )
        nodes.setdefault(node_id, node)
        return nodes[node_id]

    def add_edge(
        source_node_id: str,
        edge_type: EdgeType,
        target_node_id: str,
        provenance: str,
        *,
        source_entity_id: str | None = None,
        source_record: Any = None,
    ) -> None:
        identity = f"{source_node_id}|{edge_type.value}|{target_node_id}"
        edge_id = f"edge_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"
        pending_edges.setdefault(
            edge_id,
            GraphEdge(
                id=edge_id,
                source_node_id=source_node_id,
                edge_type=edge_type,
                target_node_id=target_node_id,
                created_at=created_at,
                provenance=provenance,
                source_entity_id=source_entity_id,
                source_hash=_hash(source_record) if source_record is not None else None,
            ),
        )

    rc_node = add_node(NodeType.RESEARCH_CASE, research_case_id, "Research Case", "research_cases")
    analysis = analyze_response.get("analysis") or {}
    paper = analysis.get("paper") or {}
    paper_id = f"paper_{research_case_id}"
    paper_node = add_node(
        NodeType.PAPER,
        paper_id,
        paper.get("title") or "Paper",
        "research_cases.analysis.paper",
        paper,
    )
    add_edge(rc_node.id, EdgeType.CONTAINS, paper_node.id, "structural")

    claim_records: dict[str, dict[str, Any]] = {}
    for claim in analysis.get("claims", []):
        if isinstance(claim, dict) and (claim_id := _entity_id(claim, "id", "claim_id")):
            claim_records[claim_id] = claim
    for claim in (analyze_response.get("research_case") or {}).get("claims", []):
        if isinstance(claim, dict) and (claim_id := _entity_id(claim, "id", "claim_id")):
            claim_records.setdefault(claim_id, claim)
    for claim_id, claim in claim_records.items():
        text = claim.get("claim_text") or claim.get("description") or claim_id
        claim_node = add_node(
            NodeType.CLAIM,
            claim_id,
            f"Claim: {text[:50]}",
            "research_cases.analysis.claims",
            claim,
        )
        add_edge(paper_node.id, EdgeType.HAS_CLAIM, claim_node.id, "structural")

    # Authoritative source: AnalyzePaperResponse.analysis.experiments.
    experiment_records: dict[str, dict[str, Any]] = {}
    for experiment in analysis.get("experiments", []):
        if not isinstance(experiment, dict) or not (experiment_id := _entity_id(experiment, "id")):
            continue
        experiment_records[experiment_id] = experiment
        experiment_node = add_node(
            NodeType.EXPERIMENT,
            experiment_id,
            f"Experiment: {experiment.get('objective') or experiment_id}",
            "research_cases.analysis.experiments",
            experiment,
        )
        add_edge(
            paper_node.id,
            EdgeType.HAS_EXPERIMENT,
            experiment_node.id,
            "research_cases.analysis.experiments",
            source_entity_id=experiment_id,
            source_record=experiment,
        )

    # Authoritative source: persisted Reference records. Provider/locator strings
    # remain attributes and are never promoted to source identities.
    reference_records: dict[str, dict[str, Any]] = {}
    for reference in analysis.get("references", []):
        if not isinstance(reference, dict) or not (reference_id := _entity_id(reference, "id")):
            continue
        reference_records[reference_id] = reference
        source_node = add_node(
            NodeType.SOURCE,
            reference_id,
            f"Source: {reference.get('title') or reference.get('citation_text') or reference_id}",
            "research_cases.analysis.references",
            reference,
        )
        add_edge(
            paper_node.id,
            EdgeType.CITES,
            source_node.id,
            "research_cases.analysis.references",
            source_entity_id=reference_id,
            source_record=reference,
        )

    # Support edges require an explicit assessment. Association alone cannot be
    # upgraded into scientific support.
    assessments_by_evidence: dict[str, tuple[EdgeType, dict[str, Any]]] = {}
    for assessment in analyze_response.get("claim_evidence", []):
        if not isinstance(assessment, dict):
            continue
        edge_type = {
            "SUPPORTED": EdgeType.SUPPORTED_BY,
            "PARTIALLY_SUPPORTED": EdgeType.PARTIALLY_SUPPORTED_BY,
        }.get(assessment.get("support_status"))
        if edge_type is None:
            continue
        for evidence_id in assessment.get("evidence_ids", []):
            if isinstance(evidence_id, str) and evidence_id:
                assessments_by_evidence[evidence_id] = (edge_type, assessment)

    # Authoritative source: AnalyzePaperResponse.evidence_items. The complete
    # metadata (including classification) is copied verbatim.
    for evidence in analyze_response.get("evidence_items", []):
        if not isinstance(evidence, dict) or not (
            evidence_id := _entity_id(evidence, "evidence_id")
        ):
            continue
        evidence_node = add_node(
            NodeType.EVIDENCE,
            evidence_id,
            f"Evidence: {evidence.get('source_title') or evidence.get('evidence_type') or evidence_id}",
            "research_cases.evidence_items",
            evidence,
        )
        claim_id = _entity_id(evidence, "claim_id")
        support = assessments_by_evidence.get(evidence_id)
        if claim_id and support and support[1].get("claim_id") == claim_id:
            edge_type, assessment = support
            add_edge(
                generate_id("CLAIM", claim_id),
                edge_type,
                evidence_node.id,
                "research_cases.claim_evidence",
                source_entity_id=claim_id,
                source_record=assessment,
            )
        reference_id = _entity_id(evidence, "reference_id")
        if reference_id and reference_id in reference_records:
            add_edge(
                evidence_node.id,
                EdgeType.DERIVED_FROM,
                generate_id("SOURCE", reference_id),
                "research_cases.evidence_items.reference_id",
                source_entity_id=evidence_id,
                source_record=evidence,
            )

    for artifact in analyze_response.get("artifacts", []):
        if not isinstance(artifact, dict) or not (
            artifact_id := _entity_id(artifact, "artifact_id", "id")
        ):
            continue
        artifact_node = add_node(
            NodeType.ARTIFACT,
            artifact_id,
            f"Artifact: {artifact.get('name') or artifact_id}",
            "research_cases.artifacts",
            artifact,
        )
        add_edge(paper_node.id, EdgeType.CONTAINS, artifact_node.id, "structural")

    targets = (analyze_response.get("reproduction_targets") or {}).get("candidate_targets", [])
    for target in targets:
        if not isinstance(target, dict) or not (target_id := _entity_id(target, "target_id")):
            continue
        target_node = add_node(
            NodeType.REPRODUCTION_TARGET,
            target_id,
            f"Target: {target.get('objective') or target.get('name') or target_id}",
            "research_cases.reproduction_targets",
            target,
        )
        experiment_id = _entity_id(target, "experiment_id")
        if experiment_id and experiment_id in experiment_records:
            add_edge(
                generate_id("EXPERIMENT", experiment_id),
                EdgeType.MAPS_TO,
                target_node.id,
                "research_cases.reproduction_targets.experiment_id",
                source_entity_id=target_id,
                source_record=target,
            )
            published_result = target.get("published_result") or {}
            source_claim_id = _entity_id(published_result, "source_claim_id")
            if source_claim_id:
                add_edge(
                    generate_id("CLAIM", source_claim_id),
                    EdgeType.MAPS_TO,
                    generate_id("EXPERIMENT", experiment_id),
                    "research_cases.reproduction_targets.published_result.source_claim_id",
                    source_entity_id=target_id,
                    source_record=published_result,
                )
        if code_artifact_id := _entity_id(target, "code_artifact_id"):
            add_edge(
                target_node.id,
                EdgeType.USES_ARTIFACT,
                generate_id("ARTIFACT", code_artifact_id),
                "structural",
            )

        for run in db.list("runs", target_id):
            run_id = _entity_id(run, "run_id", "id") if isinstance(run, dict) else None
            if not run_id:
                continue
            run_node = add_node(NodeType.EXECUTION, run_id, f"Run: {run_id}", "runs", run)
            add_edge(target_node.id, EdgeType.EXECUTED_AS, run_node.id, "runs")

        try:
            with db._connect() as connection:
                rows = connection.execute(
                    "SELECT payload FROM observed_results WHERE target_id=?", (target_id,)
                ).fetchall()
            observed_results = [json.loads(row[0]) for row in rows]
        except Exception:
            observed_results = []
        for observed in observed_results:
            observed_id = _entity_id(observed, "observed_result_id", "observed_id")
            if not observed_id:
                continue
            observed_node = add_node(
                NodeType.OBSERVED_RESULT,
                observed_id,
                f"Observed: {observed_id}",
                "observed_results",
                observed,
            )
            if run_id := _entity_id(observed, "run_id"):
                add_edge(generate_id("EXECUTION", run_id), EdgeType.PRODUCED, observed_node.id, "observed_results.run_id")

        for comparison in db.list("comparisons", target_id):
            comparison_id = _entity_id(comparison, "comparison_id") if isinstance(comparison, dict) else None
            if not comparison_id:
                continue
            comparison_node = add_node(
                NodeType.COMPARISON,
                comparison_id,
                f"Comparison: {comparison_id}",
                "comparisons",
                comparison,
            )
            if observed_id := _entity_id(comparison, "observed_result_id"):
                add_edge(generate_id("OBSERVED_RESULT", observed_id), EdgeType.COMPARED_WITH,
                         comparison_node.id, "comparisons.observed_result_id",
                         source_entity_id=comparison_id, source_record=comparison)
            for discrepancy in comparison.get("discrepancies", []):
                discrepancy_id = _entity_id(discrepancy, "discrepancy_id") if isinstance(discrepancy, dict) else None
                if not discrepancy_id:
                    continue
                discrepancy_node = add_node(
                    NodeType.DISCREPANCY,
                    discrepancy_id,
                    f"Discrepancy: {(discrepancy.get('description') or discrepancy_id)[:50]}",
                    "comparisons",
                    discrepancy,
                )
                add_edge(comparison_node.id, EdgeType.GENERATED_DISCREPANCY, discrepancy_node.id, "comparisons.discrepancies")

        for investigation in db.investigations(target_id):
            investigation_id = _entity_id(investigation, "investigation_id") if isinstance(investigation, dict) else None
            if not investigation_id:
                continue
            investigation_node = add_node(
                NodeType.INVESTIGATION,
                investigation_id,
                f"Investigation: {investigation_id}",
                "investigations",
                investigation,
            )
            discrepancy_id = _entity_id(investigation, "discrepancy_id")
            discrepancy_path = "investigations.discrepancy_id"
            # Step 9 stores the discrepancy body inside the investigation.
            discrepancy = investigation.get("discrepancy")
            if isinstance(discrepancy, dict) and (nested_id := _entity_id(discrepancy, "discrepancy_id")):
                discrepancy_id = nested_id
                discrepancy_path = "investigations.discrepancy.discrepancy_id"
                discrepancy_node = add_node(NodeType.DISCREPANCY, nested_id,
                                            f"Discrepancy: {discrepancy.get('statement', nested_id)[:50]}",
                                            "investigations.discrepancy", discrepancy)
                if comparison_id := _entity_id(discrepancy, "comparison_id"):
                    add_edge(generate_id("COMPARISON", comparison_id), EdgeType.GENERATED_DISCREPANCY,
                             discrepancy_node.id, "investigations.discrepancy.comparison_id",
                             source_entity_id=nested_id, source_record=discrepancy)
            if discrepancy_id:
                add_edge(generate_id("DISCREPANCY", discrepancy_id), EdgeType.INVESTIGATES,
                         investigation_node.id, discrepancy_path,
                         source_entity_id=investigation_id, source_record=investigation)

            # A plan ID on an execution is not a plan body. Only project the
            # validated authoritative body retained by the investigation.
            plan_ids = set()
            for record in investigation.get("diagnostic_plans", []):
                plan = DiagnosticPlan.model_validate(record)
                plan_ids.add(plan.diagnostic_plan_id)
                metadata = plan.model_dump(mode="json", include={
                    "diagnostic_plan_id", "hypothesis_id", "objective", "question",
                    "test_type", "change_type", "decision_rule", "status", "created_at",
                })
                plan_node = add_node(NodeType.DIAGNOSTIC_PLAN, plan.diagnostic_plan_id,
                                     f"Diagnostic plan: {plan.objective}",
                                     "investigations.diagnostic_plans", metadata)
                add_edge(generate_id("HYPOTHESIS", plan.hypothesis_id), EdgeType.HAS_DIAGNOSTIC_PLAN,
                         plan_node.id, "investigations.diagnostic_plans.hypothesis_id",
                         source_entity_id=plan.diagnostic_plan_id, source_record=record)

            for diagnostic in db.diagnostic_executions(investigation_id):
                diagnostic_id = _entity_id(diagnostic, "diagnostic_execution_id", "execution_id") if isinstance(diagnostic, dict) else None
                if not diagnostic_id:
                    continue
                diagnostic_node = add_node(
                    NodeType.DIAGNOSTIC_EXECUTION,
                    diagnostic_id,
                    f"Diagnostic: {diagnostic_id}",
                    "diagnostic_executions",
                    diagnostic,
                )
                add_edge(investigation_node.id, EdgeType.EXECUTED_DIAGNOSTIC, diagnostic_node.id, "diagnostic_executions.investigation_id")
                if (plan_id := _entity_id(diagnostic, "diagnostic_plan_id")) in plan_ids:
                    add_edge(generate_id("DIAGNOSTIC_PLAN", plan_id), EdgeType.EXECUTED_DIAGNOSTIC,
                             diagnostic_node.id, "diagnostic_executions.diagnostic_plan_id",
                             source_entity_id=diagnostic_id, source_record=diagnostic)
                if observed_id := _entity_id(diagnostic, "observed_result_id"):
                    add_edge(diagnostic_node.id, EdgeType.PRODUCED, generate_id("OBSERVED_RESULT", observed_id),
                             "diagnostic_executions.observed_result_id",
                             source_entity_id=diagnostic_id, source_record=diagnostic)

            if discrepancy_id or investigation.get("hypotheses"):
                try:
                    with db._connect() as connection:
                        rows = connection.execute(
                            "SELECT payload FROM hypotheses WHERE discrepancy_id=?", (discrepancy_id,)
                        ).fetchall()
                        hypotheses_by_id = {h["hypothesis_id"]: h for h in investigation.get("hypotheses", [])}
                        hypotheses_by_id.update({h["hypothesis_id"]: h for h in (json.loads(row[0]) for row in rows)})
                        hypotheses = list(hypotheses_by_id.values())
                        for hypothesis in hypotheses:
                            hypothesis_id = _entity_id(hypothesis, "hypothesis_id")
                            if not hypothesis_id:
                                continue
                            hypothesis_node = add_node(
                                NodeType.HYPOTHESIS,
                                hypothesis_id,
                                f"Hypothesis: {(hypothesis.get('statement') or hypothesis.get('description') or hypothesis_id)[:50]}",
                                "hypotheses",
                                hypothesis,
                            )
                            add_edge(investigation_node.id, EdgeType.HAS_HYPOTHESIS, hypothesis_node.id, "hypotheses.discrepancy_id")
                            if hypothesis_discrepancy_id := _entity_id(hypothesis, "discrepancy_id"):
                                add_edge(generate_id("DISCREPANCY", hypothesis_discrepancy_id), EdgeType.HAS_HYPOTHESIS,
                                         hypothesis_node.id, "hypotheses.discrepancy_id",
                                         source_entity_id=hypothesis_id, source_record=hypothesis)
                            test_rows = connection.execute(
                                "SELECT payload FROM hypothesis_tests WHERE hypothesis_id=?", (hypothesis_id,)
                            ).fetchall()
                            for test in (json.loads(row[0]) for row in test_rows):
                                test_id = _entity_id(test, "hypothesis_test_id", "id")
                                if not test_id:
                                    continue
                                test_node = add_node(NodeType.HYPOTHESIS_TEST, test_id, f"Test: {test_id}", "hypothesis_tests", test)
                                add_edge(hypothesis_node.id, EdgeType.TESTED_BY, test_node.id, "hypothesis_tests.hypothesis_id")
                                if diagnostic_id := _entity_id(test, "diagnostic_execution_id"):
                                    add_edge(generate_id("DIAGNOSTIC_EXECUTION", diagnostic_id), EdgeType.TEST_RESULT, test_node.id, "hypothesis_tests.diagnostic_execution_id")
                                if observed_id := _entity_id(test, "diagnostic_observed_result_id"):
                                    add_edge(generate_id("OBSERVED_RESULT", observed_id), EdgeType.TEST_RESULT,
                                             test_node.id, "hypothesis_tests.diagnostic_observed_result_id",
                                             source_entity_id=test_id, source_record=test)
                except Exception:
                    pass

    # Do not synthesize endpoints: unsupported relationships are simply absent.
    edges = {
        edge_id: edge
        for edge_id, edge in pending_edges.items()
        if edge.source_node_id in nodes and edge.target_node_id in nodes
    }
    sorted_nodes = tuple(nodes[node_id] for node_id in sorted(nodes))
    sorted_edges = tuple(edges[edge_id] for edge_id in sorted(edges))
    hash_material = {
        "graph_version": "1.1",
        "research_case_id": research_case_id,
        "nodes": [
            {
                "id": node.id,
                "node_type": node.node_type.value,
                "entity_id": node.entity_id,
                "label": node.label,
                "source_table": node.source_table,
                "source_hash": node.source_hash,
                "metadata": node.metadata,
            }
            for node in sorted_nodes
        ],
        "edges": [
            {
                "id": edge.id,
                "source_node_id": edge.source_node_id,
                "edge_type": edge.edge_type.value,
                "target_node_id": edge.target_node_id,
                "provenance": edge.provenance,
                "source_entity_id": edge.source_entity_id,
                "source_hash": edge.source_hash,
            }
            for edge in sorted_edges
        ],
    }
    graph_hash = _hash(hash_material)
    return GraphSnapshot(
        graph_snapshot_id=f"graph_{graph_hash[:32]}",
        research_case_id=research_case_id,
        graph_version="1.1",
        generated_at=created_at,
        graph_hash=graph_hash,
        node_count=len(sorted_nodes),
        edge_count=len(sorted_edges),
        nodes=sorted_nodes,
        edges=sorted_edges,
    )
