import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.graph import EdgeType, NodeType
from app.services.execution.persistence import ExecutionRepository
from app.services.execution.sandbox import execution_service
from app.services.graph_builder import build_graph

client = TestClient(app)

def test_graph_not_found():
    response = client.get("/api/v1/graph/nonexistent")
    assert response.status_code == 404

def test_graph_builder(tmp_path):
    # Setup test data
    rc_id = "rc_123"
    rc_payload = {
        "research_case": {
            "case_id": rc_id,
            "claims": [{"id": "c1", "description": "Claim 1"}],
        },
        "artifacts": [{"id": "a1", "name": "code.zip"}],
        "reproduction_targets": {
            "candidate_targets": [{"target_id": "t1", "name": "Exp 1", "code_artifact_id": "a1"}]
        }
    }
    execution_service.repository.put_research_case(rc_id, rc_payload, "2023-01-01T00:00:00Z")
    
    # Mock some DB data
    execution_service.repository.put("runs", "r1", "t1", {"id": "r1"}, "COMPLETED", "2023-01-01T00:00:00Z")
    execution_service.repository.put_observed_result("ob1", "t1", "r1", {"observed_id": "ob1", "run_id": "r1"}, "2023-01-01T00:00:00Z")
    
    response = client.get(f"/api/v1/graph/{rc_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["research_case_id"] == rc_id
    nodes = {n["id"]: n for n in data["nodes"]}
    assert "RESEARCH_CASE_rc_123" in nodes
    assert "CLAIM_c1" in nodes
    assert "ARTIFACT_a1" in nodes
    assert "REPRODUCTION_TARGET_t1" in nodes
    assert "EXECUTION_r1" in nodes
    assert "OBSERVED_RESULT_ob1" in nodes

def test_graph_provenance(tmp_path):
    rc_id = "rc_123"
    response = client.get(f"/api/v1/graph/{rc_id}/provenance/OBSERVED_RESULT_ob1")
    assert response.status_code == 200
    data = response.json()
    assert data["node"]["id"] == "OBSERVED_RESULT_ob1"
    assert len(data["in_edges"]) == 1
    assert data["in_edges"][0]["source_node_id"] == "EXECUTION_r1"


def _authoritative_payload():
    return {
        "analysis": {
            "paper": {"title": "A reproducibility study"},
            "claims": [
                {
                    "id": "CLM-1",
                    "claim_text": "The reported model improves accuracy.",
                    "claim_type": "RESULT",
                }
            ],
            "experiments": [
                {
                    "id": "EXP-1",
                    "objective": "Evaluate accuracy",
                    "metric": "accuracy",
                    "reported_result": 0.91,
                }
            ],
            "references": [
                {
                    "id": "REF-1",
                    "citation_text": "Author et al. (2025)",
                    "title": "Authoritative source",
                }
            ],
        },
        "evidence_items": [
            {
                "evidence_id": "EVD-1",
                "claim_id": "CLM-1",
                "reference_id": "REF-1",
                "evidence_type": "ABSTRACT",
                "source": "crossref",
                "source_title": "Authoritative source",
                "classification": "AUTHOR_CLAIM",
            }
        ],
        "claim_evidence": [
            {
                "claim_id": "CLM-1",
                "support_status": "SUPPORTED",
                "evidence_ids": ["EVD-1"],
            }
        ],
        "artifacts": [{"artifact_id": "ART-1", "name": "code"}],
        "reproduction_targets": {
            "candidate_targets": [
                {
                    "target_id": "TGT-1",
                    "experiment_id": "EXP-1",
                    "code_artifact_id": "ART-1",
                    "published_result": {"source_claim_id": "CLM-1"},
                }
            ]
        },
    }


def test_authoritative_experiment_evidence_source_projection_is_deterministic(tmp_path):
    repository = ExecutionRepository(tmp_path / "graph.db")
    payload = _authoritative_payload()
    repository.put_research_case("CASE-1", payload, "2026-10-06T00:00:00Z")
    persisted_payload = repository.load_research_case("CASE-1")
    assert persisted_payload is not None

    graph = build_graph("CASE-1", persisted_payload, repository)
    rebuilt = build_graph("CASE-1", repository.load_research_case("CASE-1"), repository)
    nodes = {node.id: node for node in graph.nodes}
    edges = {
        (edge.source_node_id, edge.edge_type, edge.target_node_id): edge
        for edge in graph.edges
    }

    assert nodes["EXPERIMENT_EXP-1"].entity_id == "EXP-1"
    assert nodes["EVIDENCE_EVD-1"].entity_id == "EVD-1"
    assert nodes["SOURCE_REF-1"].entity_id == "REF-1"
    assert nodes["EVIDENCE_EVD-1"].metadata["classification"] == "AUTHOR_CLAIM"
    assert (
        "PAPER_paper_CASE-1",
        EdgeType.HAS_EXPERIMENT,
        "EXPERIMENT_EXP-1",
    ) in edges
    assert ("CLAIM_CLM-1", EdgeType.SUPPORTED_BY, "EVIDENCE_EVD-1") in edges
    assert ("EVIDENCE_EVD-1", EdgeType.DERIVED_FROM, "SOURCE_REF-1") in edges
    assert ("EXPERIMENT_EXP-1", EdgeType.MAPS_TO, "REPRODUCTION_TARGET_TGT-1") in edges
    assert edges[("CLAIM_CLM-1", EdgeType.SUPPORTED_BY, "EVIDENCE_EVD-1")].provenance == "research_cases.claim_evidence"

    assert len(nodes) == graph.node_count
    assert len({edge.id for edge in graph.edges}) == graph.edge_count
    assert all(edge.source_node_id in nodes and edge.target_node_id in nodes for edge in graph.edges)
    assert graph.graph_hash == rebuilt.graph_hash
    assert graph.graph_snapshot_id == rebuilt.graph_snapshot_id
    assert [node.id for node in graph.nodes] == [node.id for node in rebuilt.nodes]
    assert [edge.id for edge in graph.edges] == [edge.id for edge in rebuilt.edges]


def test_projection_does_not_fabricate_sources_or_support_edges(tmp_path):
    repository = ExecutionRepository(tmp_path / "anti-fabrication.db")
    payload = _authoritative_payload()
    payload["analysis"]["references"] = []
    payload["claim_evidence"][0]["support_status"] = "UNCLEAR"

    graph = build_graph("CASE-2", payload, repository)
    nodes = {node.id: node for node in graph.nodes}
    edges = {(edge.source_node_id, edge.edge_type, edge.target_node_id) for edge in graph.edges}

    assert "EVIDENCE_EVD-1" in nodes
    assert not any(node.node_type == NodeType.SOURCE for node in graph.nodes)
    assert "SOURCE_crossref" not in nodes
    assert not any(edge_type in {EdgeType.SUPPORTED_BY, EdgeType.PARTIALLY_SUPPORTED_BY} for _, edge_type, _ in edges)
    assert not any(source == "EVIDENCE_EVD-1" and target.startswith("SOURCE_") for source, _, target in edges)
