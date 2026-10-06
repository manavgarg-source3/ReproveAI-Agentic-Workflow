import pytest
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.diagnostic import DiagnosticDecisionRule
from app.schemas.execution import ExecutionPolicy, ExecutionRecord, ExecutionStatus
from app.schemas.investigation import DiagnosticPlan, DiagnosticPlanStatus, Hypothesis, HypothesisStatus, DiscrepancyCategory
from app.services.execution.diagnostic import DiagnosticOrchestrator
from app.services.execution.persistence import ExecutionRepository
from app.services.execution.sandbox import ExecutionService, DockerRunner
from app.services.graph_builder import build_graph, generate_id
from app.schemas.graph import NodeType, EdgeType
from tests.test_secure_execution import target, code_artifact
from tests.test_result_comparison import target_with_published
from app.schemas.research import ObservedResult
from app.services.execution.comparison import compare_result
from app.services.execution.investigation import investigate
from app.services.execution.evaluator import evaluate_diagnostic

def _now():
    return datetime.now(timezone.utc)

def test_full_chain_graph_materialization_and_provenance(tmp_path: Path):
    repo_db = tmp_path / "e2e.db"
    repo = ExecutionRepository(repo_db)
    runner = DockerRunner()
    service = ExecutionService(runner=runner, db_path=repo_db)
    
    # 1. Create Research Case (Paper, Claim, Artifact)
    case_id = "CASE-E2E-123"
    paper_id = "P-1"
    claim_id = "C-1"
    artifact_id = "ART-FIXTURE"
    
    rc_payload = {
        "analysis": {
            "paper": {"title": "Persisted E2E paper"},
            "claims": [{"id": claim_id, "claim_text": "Proposed claim", "claim_type": "RESULT"}],
            "experiments": [{"id": "EXP-FIXTURE", "objective": "Evaluate the persisted fixture", "metric": "accuracy"}],
            "references": [{"id": "REF-1", "citation_text": "Fixture reference", "title": "Fixture source"}],
        },
        "research_case": {
            "case_id": case_id,
            "paper_id": paper_id,
            "claims": [{"claim_id": claim_id, "description": "Proposed claim"}]
        },
        "evidence_items": [{
            "evidence_id": "EVD-1",
            "claim_id": claim_id,
            "reference_id": "REF-1",
            "evidence_type": "ABSTRACT",
            "source": "fixture-provider",
            "classification": "AUTHOR_CLAIM",
        }],
        "claim_evidence": [{
            "claim_id": claim_id,
            "support_status": "SUPPORTED",
            "evidence_ids": ["EVD-1"],
        }],
        "artifacts": [{"artifact_id": artifact_id, "name": "code.zip"}],
        "reproduction_targets": {
            "candidate_targets": []
        }
    }
    
    # Setup baseline target and artifacts
    t = target_with_published(value=0.90)
    t = t.model_copy(update={"target_id": "T-1"})
    t = t.model_copy(update={"published_result": t.published_result.model_copy(update={"source_claim_id": claim_id})})
    
    rc_payload["reproduction_targets"]["candidate_targets"].append(t.model_dump(mode="json"))
    
    repo.put_research_case(case_id, rc_payload, _now().isoformat().replace("+00:00", "Z"))
    
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    (artifact_dir / "evaluate.py").write_text("import json; open('/outputs/result.json', 'w').write(json.dumps({'metric': 'accuracy', 'value': 0.50}))")
    (tmp_path / "input.json").write_text("{}")
    
    service.register_selection(type("Sel", (), {"candidate_targets": [t], "selected_target_id": t.target_id, "selected_target": t})(), [code_artifact()])
    service.register_artifact_source(t.target_id, artifact_dir)
    service.register_input(t.target_id, "INPUT-FIXTURE", "input.json", tmp_path / "input.json")
    
    # Run baseline execution (Execution -> Observed Result)
    policy = ExecutionPolicy(runtime_limit_seconds=10)
    approval = service.approve(t.target_id, "reviewer", policy)
    baseline_run = service.execute(t.target_id, approval.approval_id, policy)
    assert baseline_run.status == "COMPLETED"
    
    from app.services.execution.extraction import extract_observed_result
    observed = extract_observed_result(t, baseline_run)
    repo.put_observed_result(observed.observed_result_id, t.target_id, baseline_run.run_id, observed.model_dump(), _now().isoformat().replace("+00:00", "Z"))
    
    comparison = compare_result(t, baseline_run, observed, tolerance=0.01, tolerance_basis="Deterministic fixture tolerance")
    repo.put_comparison(comparison.comparison_id, baseline_run.run_id, t.target_id,
                        comparison.model_dump(mode="json"), _now().isoformat())
    investigation = investigate(t, baseline_run, comparison)
    assert investigation.discrepancy is not None
    hypothesis = investigation.hypotheses[0]
    hyp_id = hypothesis.hypothesis_id
    # Existing Step 10A uses plan.hypothesis_id as approval.investigation_id.
    # Match that established fixture convention without changing execution.
    inv_id = hyp_id
    
    # Diagnostic Orchestration
    orchestrator = DiagnosticOrchestrator(service, repo)
    plan = DiagnosticPlan(
        diagnostic_plan_id="DP-123",
        hypothesis_id=hyp_id,
        objective="Test increase",
        question="Does parameter=2 increase metric?",
        test_type="CONTROLLED_DIAGNOSTIC",
        change_type="CODE_PATCH",
        target_path="evaluate.py",
        original_state="0.50",
        proposed_state="0.75",
        decision_rule=DiagnosticDecisionRule.METRIC_INCREASES,
        alternative_observation="metric decreases or stays same",
        status=DiagnosticPlanStatus.READY,
        created_at=_now()
    )
    hypothesis = hypothesis.model_copy(update={"diagnostic_plan_ids": (plan.diagnostic_plan_id,)})
    investigation = investigation.model_copy(update={
        "investigation_id": inv_id,
        "hypotheses": (hypothesis,),
        "diagnostic_plans": (plan,),
        "discrepancy": investigation.discrepancy.model_copy(update={
            "hypothesis_ids": (hyp_id,), "diagnostic_plan_ids": (plan.diagnostic_plan_id,),
        }),
    })
    repo.put_investigation(inv_id, t.target_id, investigation.model_dump(mode="json"), _now().isoformat())
    repo.put_hypothesis(hyp_id, hypothesis.discrepancy_id, hypothesis.model_dump(mode="json"),
                        hypothesis.status.value, _now().isoformat())
    persisted_plan = repo.investigations(t.target_id)[0]["diagnostic_plans"][0]
    assert DiagnosticPlan.model_validate(persisted_plan) == plan
    
    diag_approval = orchestrator.approve_diagnostic(plan, t, baseline_run.run_id, "diag-reviewer")
    execution = orchestrator.execute_diagnostic(diag_approval, plan, t, policy)
    assert execution.status.value == "COMPLETED"
    
    diagnostic_run = ExecutionRecord.model_validate(repo.load("runs", execution.sandbox_run_id))
    diagnostic_observed = ObservedResult.model_validate(repo.load_observed_result(t.target_id, execution.sandbox_run_id))
    assert diagnostic_observed.value == 0.75
    diagnostic_comparison = compare_result(t, diagnostic_run, diagnostic_observed,
                                          tolerance=0.01, tolerance_basis="Deterministic fixture tolerance")
    repo.put_comparison(diagnostic_comparison.comparison_id, diagnostic_run.run_id, t.target_id,
                        diagnostic_comparison.model_dump(mode="json"), _now().isoformat())
    followup = investigate(t, diagnostic_run, diagnostic_comparison)
    assert followup.discrepancy is not None
    repo.put_investigation(followup.investigation_id, t.target_id, followup.model_dump(mode="json"), _now().isoformat())
    for candidate in followup.hypotheses:
        repo.put_hypothesis(candidate.hypothesis_id, candidate.discrepancy_id,
                            candidate.model_dump(mode="json"), candidate.status.value, _now().isoformat())
    test_record = evaluate_diagnostic(repo, execution.diagnostic_execution_id)
    assert test_record.resulting_status == "SUPPORTED"
    
    # Graph Materialization
    persisted_payload = repo.load_research_case(case_id)
    assert persisted_payload is not None
    graph = build_graph(case_id, persisted_payload, repo)
    
    node_ids = set()
    node_types = set()
    for n in graph.nodes:
        assert n.id not in node_ids, f"Duplicate node: {n.id}"
        node_ids.add(n.id)
        node_types.add(n.node_type)
        
    edge_ids = set()
    for e in graph.edges:
        assert e.id not in edge_ids, f"Duplicate edge: {e.id}"
        edge_ids.add(e.id)
        assert e.source_node_id in node_ids, f"Broken edge source: {e.source_node_id}"
        assert e.target_node_id in node_ids, f"Broken edge target: {e.target_node_id}"
        
    required_types = {
        NodeType.CLAIM,
        NodeType.EXPERIMENT,
        NodeType.EVIDENCE,
        NodeType.SOURCE,
        NodeType.REPRODUCTION_TARGET,
        NodeType.ARTIFACT,
        NodeType.EXECUTION,
        NodeType.OBSERVED_RESULT,
        NodeType.COMPARISON,
        NodeType.DISCREPANCY,
        NodeType.INVESTIGATION,
        NodeType.DIAGNOSTIC_EXECUTION,
        NodeType.HYPOTHESIS_TEST
    }
    required_types.update({NodeType.HYPOTHESIS, NodeType.DIAGNOSTIC_PLAN})
    
    for t_enum in required_types:
        assert t_enum in node_types, f"Missing required node type: {t_enum}"
        
    # Idempotency
    graph2 = build_graph(case_id, repo.load_research_case(case_id), repo)
    assert graph.node_count == graph2.node_count
    assert graph.edge_count == graph2.edge_count
    assert graph.graph_hash == graph2.graph_hash
    assert graph.graph_snapshot_id == graph2.graph_snapshot_id
    assert [n.id for n in graph.nodes] == [n.id for n in graph2.nodes]
    assert [e.id for e in graph.edges] == [e.id for e in graph2.edges]

    edge_triples = {
        (edge.source_node_id, edge.edge_type, edge.target_node_id)
        for edge in graph.edges
    }
    assert ("CLAIM_C-1", EdgeType.SUPPORTED_BY, "EVIDENCE_EVD-1") in edge_triples
    assert ("EVIDENCE_EVD-1", EdgeType.DERIVED_FROM, "SOURCE_REF-1") in edge_triples
    assert (
        "PAPER_paper_CASE-E2E-123",
        EdgeType.HAS_EXPERIMENT,
        "EXPERIMENT_EXP-FIXTURE",
    ) in edge_triples
    assert (
        "EXPERIMENT_EXP-FIXTURE",
        EdgeType.MAPS_TO,
        "REPRODUCTION_TARGET_T-1",
    ) in edge_triples

    def require_path(steps):
        for source, edge_type, destination in steps:
            assert (source, edge_type, destination) in edge_triples, (source, edge_type, destination)

    nid = generate_id
    require_path([
        ("CLAIM_C-1", EdgeType.MAPS_TO, "EXPERIMENT_EXP-FIXTURE"),
        ("REPRODUCTION_TARGET_T-1", EdgeType.EXECUTED_AS, nid("EXECUTION", baseline_run.run_id)),
        (nid("EXECUTION", baseline_run.run_id), EdgeType.PRODUCED, nid("OBSERVED_RESULT", observed.observed_result_id)),
        (nid("OBSERVED_RESULT", observed.observed_result_id), EdgeType.COMPARED_WITH, nid("COMPARISON", comparison.comparison_id)),
        (nid("COMPARISON", comparison.comparison_id), EdgeType.GENERATED_DISCREPANCY, nid("DISCREPANCY", hypothesis.discrepancy_id)),
        (nid("DISCREPANCY", hypothesis.discrepancy_id), EdgeType.INVESTIGATES, nid("INVESTIGATION", inv_id)),
        (nid("INVESTIGATION", inv_id), EdgeType.HAS_HYPOTHESIS, nid("HYPOTHESIS", hyp_id)),
        (nid("HYPOTHESIS", hyp_id), EdgeType.HAS_DIAGNOSTIC_PLAN, "DIAGNOSTIC_PLAN_DP-123"),
        ("DIAGNOSTIC_PLAN_DP-123", EdgeType.EXECUTED_DIAGNOSTIC, nid("DIAGNOSTIC_EXECUTION", execution.diagnostic_execution_id)),
        (nid("DIAGNOSTIC_EXECUTION", execution.diagnostic_execution_id), EdgeType.PRODUCED, nid("OBSERVED_RESULT", diagnostic_observed.observed_result_id)),
        (nid("OBSERVED_RESULT", diagnostic_observed.observed_result_id), EdgeType.TEST_RESULT, nid("HYPOTHESIS_TEST", test_record.id)),
    ])
    # Trace test <- diagnostic -> observation -> comparison -> discrepancy ->
    # hypothesis <- investigation. Reverse hops use existing edge semantics.
    require_path([
        (nid("DIAGNOSTIC_EXECUTION", execution.diagnostic_execution_id), EdgeType.TEST_RESULT, nid("HYPOTHESIS_TEST", test_record.id)),
        (nid("OBSERVED_RESULT", diagnostic_observed.observed_result_id), EdgeType.COMPARED_WITH, nid("COMPARISON", diagnostic_comparison.comparison_id)),
        (nid("COMPARISON", diagnostic_comparison.comparison_id), EdgeType.GENERATED_DISCREPANCY, nid("DISCREPANCY", followup.discrepancy.discrepancy_id)),
        (nid("DISCREPANCY", followup.discrepancy.discrepancy_id), EdgeType.HAS_HYPOTHESIS, nid("HYPOTHESIS", followup.hypotheses[0].hypothesis_id)),
        (nid("INVESTIGATION", followup.investigation_id), EdgeType.HAS_HYPOTHESIS, nid("HYPOTHESIS", followup.hypotheses[0].hypothesis_id)),
    ])
    
    # Traces
    print("Graph materialization and determinism passes!")
