"""Step 11 projection tests over existing persisted domain contracts."""
import pytest

from app.schemas.graph import EdgeType
from app.services.execution.persistence import ExecutionRepository
from app.services.execution.evaluator import evaluate_diagnostic
from app.services.execution.comparison import compare_result
from app.services.graph_builder import build_graph, generate_id
from tests.test_evaluator import create_base_data
from tests.test_result_comparison import observed, run, target_with_published


@pytest.fixture
def persisted(tmp_path):
    repo = ExecutionRepository(tmp_path / "provenance.db")
    repo, diagnostic_id, hypothesis_id, investigation_id = create_base_data(repo)
    diagnostic = repo.load_diagnostic_execution(diagnostic_id)
    result = observed().model_copy(update={"target_id": "target-1"})
    diagnostic["observed_result_id"] = result.observed_result_id
    repo.put_diagnostic_execution(diagnostic_id, diagnostic["diagnostic_plan_id"], "target-1",
                                  diagnostic, diagnostic["status"], diagnostic["created_at"])
    repo.put_observed_result(result.observed_result_id, "target-1", result.run_id,
                             result.model_dump(mode="json"), diagnostic["created_at"])
    comparison = compare_result(target_with_published().model_copy(update={"target_id": "target-1"}), run(), result)
    repo.put_comparison(comparison.comparison_id, comparison.run_id, "target-1",
                        comparison.model_dump(mode="json"), comparison.created_at.isoformat())
    test = evaluate_diagnostic(repo, diagnostic_id)
    payload = {"reproduction_targets": {"candidate_targets": [{"target_id": "target-1"}]}}
    repo.put_research_case("case", payload, diagnostic["created_at"])
    return repo, diagnostic, hypothesis_id, investigation_id, result, comparison, test


def graph_for(repo):
    return build_graph("case", repo.load_research_case("case"), repo)


def require_diagnostic_trace(graph, diagnostic, result, comparison, test):
    triples = {(e.source_node_id, e.edge_type, e.target_node_id) for e in graph.edges}
    for link in (
        (generate_id("DIAGNOSTIC_EXECUTION", diagnostic["diagnostic_execution_id"]), EdgeType.TEST_RESULT, generate_id("HYPOTHESIS_TEST", test.id)),
        (generate_id("DIAGNOSTIC_EXECUTION", diagnostic["diagnostic_execution_id"]), EdgeType.PRODUCED, generate_id("OBSERVED_RESULT", result.observed_result_id)),
        (generate_id("OBSERVED_RESULT", result.observed_result_id), EdgeType.COMPARED_WITH, generate_id("COMPARISON", comparison.comparison_id)),
    ):
        assert link in triples, f"Missing authoritative provenance link: {link}"


def test_persisted_plan_and_provenance_rebuild(persisted):
    repo, diagnostic, hypothesis_id, investigation_id, result, comparison, test = persisted
    graph = graph_for(repo)
    require_diagnostic_trace(graph, diagnostic, result, comparison, test)
    nodes = {n.id: n for n in graph.nodes}
    edges = {(e.source_node_id, e.edge_type, e.target_node_id): e for e in graph.edges}
    plan_id = generate_id("DIAGNOSTIC_PLAN", diagnostic["diagnostic_plan_id"])
    assert nodes[plan_id].source_table == "investigations.diagnostic_plans"
    assert nodes[plan_id].metadata["decision_rule"] == "METRIC_INCREASES"
    assert "original_state" not in nodes[plan_id].metadata
    assert (generate_id("HYPOTHESIS", hypothesis_id), EdgeType.HAS_DIAGNOSTIC_PLAN, plan_id) in edges
    assert (plan_id, EdgeType.EXECUTED_DIAGNOSTIC, generate_id("DIAGNOSTIC_EXECUTION", diagnostic["diagnostic_execution_id"])) in edges
    assert (generate_id("INVESTIGATION", investigation_id), EdgeType.HAS_HYPOTHESIS, generate_id("HYPOTHESIS", hypothesis_id)) in edges
    comparison_edge = edges[(generate_id("OBSERVED_RESULT", result.observed_result_id), EdgeType.COMPARED_WITH, generate_id("COMPARISON", comparison.comparison_id))]
    assert comparison_edge.provenance == "comparisons.observed_result_id"
    assert comparison_edge.source_entity_id == comparison.comparison_id
    assert comparison_edge.source_hash
    assert len(nodes) == graph.node_count
    assert len({e.id for e in graph.edges}) == graph.edge_count
    assert all(e.source_node_id in nodes and e.target_node_id in nodes for e in graph.edges)
    rebuilt = graph_for(repo)
    assert graph.graph_hash == rebuilt.graph_hash
    assert [n.id for n in graph.nodes] == [n.id for n in rebuilt.nodes]
    assert [e.id for e in graph.edges] == [e.id for e in rebuilt.edges]


def test_execution_plan_id_does_not_synthesize_plan_body(persisted):
    repo, diagnostic, _, investigation_id, *_ = persisted
    investigation = repo.investigations("target-1")[0]
    investigation["diagnostic_plans"] = []
    repo.update_investigation(investigation_id, investigation)
    graph = graph_for(repo)
    plan_id = generate_id("DIAGNOSTIC_PLAN", diagnostic["diagnostic_plan_id"])
    assert plan_id not in {n.id for n in graph.nodes}
    assert not any(e.source_node_id == plan_id or e.target_node_id == plan_id for e in graph.edges)
    with pytest.raises(AssertionError):
        assert plan_id in {n.id for n in graph.nodes}, "Missing authoritative plan body"


@pytest.mark.parametrize("missing", ["diagnostic_link", "comparison_link", "observation_body"])
def test_missing_authority_fails_trace_validation(persisted, missing):
    repo, diagnostic, _, _, result, comparison, test = persisted
    if missing == "diagnostic_link":
        diagnostic["observed_result_id"] = None
        repo.put_diagnostic_execution(diagnostic["diagnostic_execution_id"], diagnostic["diagnostic_plan_id"],
                                      "target-1", diagnostic, diagnostic["status"], diagnostic["created_at"])
    else:
        # Corrupt isolated test persistence to prove fail-closed projection;
        # no production record or scientific operation is altered.
        with repo._connect() as connection:
            if missing == "comparison_link":
                import json
                record = comparison.model_dump(mode="json")
                record["observed_result_id"] = None
                connection.execute("UPDATE comparisons SET payload=? WHERE comparison_id=?",
                                   (json.dumps(record), comparison.comparison_id))
            else:
                connection.execute("DELETE FROM observed_results WHERE observed_id=?", (result.observed_result_id,))
    graph = graph_for(repo)
    with pytest.raises(AssertionError, match="Missing authoritative provenance link"):
        require_diagnostic_trace(graph, diagnostic, result, comparison, test)
    ids = {n.id for n in graph.nodes}
    assert all(e.source_node_id in ids and e.target_node_id in ids for e in graph.edges)
    if missing == "observation_body":
        assert generate_id("OBSERVED_RESULT", result.observed_result_id) not in ids
