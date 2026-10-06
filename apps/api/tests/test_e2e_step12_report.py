"""Real Step 11 Docker/persistence flow consumed by Step 12, without rewrites."""
from app.services.assurance import generate_report
from app.services.assurance_store import ReportStore, canonical_report
from app.services.execution.persistence import ExecutionRepository
from tests.test_e2e_step11_graph import test_full_chain_graph_materialization_and_provenance as run_step11
from tests.test_assurance_reports import persist_graph, scientific_snapshot


def test_real_persisted_report_e2e(tmp_path):
    run_step11(tmp_path)
    repo = ExecutionRepository(tmp_path / "e2e.db")
    graph = persist_graph(repo, "CASE-E2E-123")
    before = scientific_snapshot(repo)
    store = ReportStore(repo.path)
    report = generate_report(store, "CASE-E2E-123", "e2e-reviewer")
    assert report.status == "NOT_REPRODUCED"
    for section in ("claim_summary", "evidence_summary", "artifact_summary", "environment_summary",
                    "reproduction_summary", "comparison_summary", "discrepancy_summary",
                    "hypothesis_summary", "diagnostic_summary", "investigation_summary", "state_transition_summary"):
        assert getattr(report, section), section
    assert report.graph_snapshot_id == graph.graph_snapshot_id
    assert report.graph_hash == graph.graph_hash
    assert report.provenance_summary["valid"], report.provenance_summary["issues"]
    assert report.hypothesis_summary[0]["epistemic_status"] == "HYPOTHESIS"
    for hypothesis in report.hypothesis_summary:
        assert hypothesis["status"] == repo.load_hypothesis(hypothesis["hypothesis_id"])["status"]
    for investigation in report.investigation_summary:
        persisted = next(i for i in repo.investigations("T-1") if i["investigation_id"] == investigation["investigation_id"])
        assert investigation["status"] == persisted["status"]
        assert investigation["final_resolution"] == ("RESOLVED" if persisted["status"] == "RESOLVED" else None)
    assert any(l["code"] == "HISTORICAL_BASELINE_REFERENCE" for l in report.limitations)
    second = generate_report(store, "CASE-E2E-123", "e2e-reviewer")
    assert canonical_report(report) == canonical_report(second)
    assert report.report_id == second.report_id
    assert scientific_snapshot(repo) == before
    assert store.get(report.report_id) == report
