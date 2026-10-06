"""Step 12 verdict, persistence, authorization, exports and read-only boundaries."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import sqlite3
import time

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.routes.reports import report_store
from app.services.assurance import generate_report, ReportInputError
from app.services.assurance_export import report_html
from app.services.assurance_store import ReportStore, canonical_report, digest
from app.services.execution.persistence import ExecutionRepository
from app.services.graph_builder import build_graph
from tests.test_graph import _authoritative_payload
from tests.test_result_comparison import target_with_published, observed, run
from app.services.execution.comparison import compare_result
from app.schemas.comparison import Compatibility, ReproductionStatus


def persist_graph(repo, case_id="CASE-REPORT"):
    graph = build_graph(case_id, repo.load_research_case(case_id), repo)
    repo.put_graph_snapshot(graph.graph_snapshot_id, case_id, graph.model_dump(mode="json"), graph.generated_at.isoformat())
    return graph


def seed(repo, outcome="VERIFIED", *, suffix="", unknown_context=False):
    tid, rid, oid = "TGT-1" + suffix, "RUN-1" + suffix, "OBS-1" + suffix
    target = target_with_published().model_copy(update={"target_id": tid, "experiment_id": "EXP-1", "code_artifact_id": "ART-1"})
    target = target.model_copy(update={"published_result": target.published_result.model_copy(update={"source_claim_id": "CLM-1"})})
    execution = run().model_copy(update={"run_id": rid, "target_id": tid, "experiment_id": "EXP-1", "artifact_id": "ART-1"})
    result = observed().model_copy(update={"observed_result_id": oid, "run_id": rid, "target_id": tid, "experiment_id": "EXP-1"})
    comparison = compare_result(target, execution, result).model_copy(update={
        "comparison_id": "CMP-1" + suffix, "reproduction_status": ReproductionStatus(outcome),
        # A unit fixture of the persisted contract, not a change to Step 8.
        "configuration_compatibility": Compatibility.UNKNOWN if unknown_context else Compatibility.MATCH,
    })
    repo.put("runs", rid, tid, execution.model_dump(mode="json"), "COMPLETED", execution.timestamp_started.isoformat())
    repo.put_observed_result(oid, tid, rid, result.model_dump(mode="json"), execution.timestamp_started.isoformat())
    repo.put_comparison(comparison.comparison_id, rid, tid, comparison.model_dump(mode="json"), comparison.created_at.isoformat())
    return target


@pytest.fixture
def saved_case(tmp_path):
    repo = ExecutionRepository(tmp_path / "reports.db")
    target = seed(repo)
    payload = _authoritative_payload()
    payload["analysis"]["experiments"][0]["reported_result"] = 0.75
    payload["reproduction_targets"]["candidate_targets"] = [target.model_dump(mode="json")]
    payload["artifacts"][0].update(availability_status="VERIFIED", relationship_status="VERIFIED", type="CODE")
    payload["evidence_items"][0]["excerpt"] = "The author reports an improvement."
    payload["reference_validation"] = [{"reference_id": "REF-1", "status": "VALID_CORRECT"}]
    payload["reproduction_plans"] = [{
        "plan_id": target.plan_id, "experiment_id": target.experiment_id,
        "status": "READY_FOR_EXECUTION", "confidence": "HIGH",
        "readiness": {"overall_status": "READY_FOR_EXECUTION", "rationale": "Controlled unit fixture"},
    }]
    repo.put_research_case("CASE-REPORT", payload, "2026-10-06T00:00:00Z")
    persist_graph(repo)
    return repo, ReportStore(repo.path), payload


def scientific_snapshot(repo):
    with repo._connect() as db:
        names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'assurance_reports'")]
        return {name: sorted(tuple(r) for r in db.execute(f"SELECT * FROM {name}")) for name in names}


@pytest.mark.parametrize("status", ["VERIFIED", "PARTIALLY_REPRODUCED", "NOT_REPRODUCED", "INCONCLUSIVE", "BLOCKED"])
def test_authoritative_statuses(saved_case, status):
    repo, store, _ = saved_case
    with repo._connect() as db:
        value = json.loads(db.execute("SELECT payload FROM comparisons").fetchone()[0])
        value["reproduction_status"] = status
        db.execute("UPDATE comparisons SET payload=?", (json.dumps(value),))
    persist_graph(repo)
    report = generate_report(store, "CASE-REPORT", "reviewer")
    assert report.status.value == status
    assert report.reproduction_summary[0]["persisted_reproduction_status"] == status
    assert report.claim_summary[0].epistemic_status.value == "AUTHOR_CLAIM"
    assert report.evidence_summary[0]["classification"] == "AUTHOR_CLAIM"


def test_report_versions_hash_and_no_scientific_writes(saved_case, monkeypatch):
    repo, store, payload = saved_case
    # Fail immediately if reporting reaches subprocess/network/LLM execution.
    def forbidden(*args, **kwargs):
        raise AssertionError("Report generation attempted external execution")
    monkeypatch.setattr("subprocess.Popen", forbidden)
    monkeypatch.setattr("socket.socket.connect", forbidden)
    before = scientific_snapshot(repo)
    first = generate_report(store, "CASE-REPORT", "reviewer")
    second = generate_report(store, "CASE-REPORT", "another-reviewer")
    assert first == second
    assert first.report_hash == digest(canonical_report(first))
    assert scientific_snapshot(repo) == before
    assert first.provenance_summary["valid"]
    assert first.graph_hash == repo.load_graph_snapshot("CASE-REPORT")["graph_hash"]
    payload["analysis"]["paper"]["title"] = "Corrected title"
    repo.put_research_case("CASE-REPORT", payload, "2026-10-06T01:00:00Z")
    with pytest.raises(ReportInputError, match="stale"):
        generate_report(store, "CASE-REPORT", "reviewer")
    persist_graph(repo)
    third = generate_report(store, "CASE-REPORT", "reviewer")
    assert third.report_version == 2
    assert third.report_hash != first.report_hash
    assert store.get(first.report_id) == first
    assert len(store.list("CASE-REPORT")) == 2


@pytest.mark.parametrize("sql", [
    "UPDATE assurance_reports SET report_hash='changed'",
    "DELETE FROM assurance_reports",
    "INSERT OR REPLACE INTO assurance_reports SELECT * FROM assurance_reports",
    "INSERT OR REPLACE INTO assurance_reports SELECT 'replacement',research_case_id,99,report_hash,payload,created_at FROM assurance_reports",
])
def test_sql_immutability(saved_case, sql):
    _, store, _ = saved_case
    report = generate_report(store, "CASE-REPORT", "reviewer")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with store.reports() as db:
            db.execute(sql)
    assert store.get(report.report_id) == report


def test_concurrent_generation_is_idempotent(saved_case):
    _, store, _ = saved_case
    with ThreadPoolExecutor(max_workers=4) as pool:
        reports = list(pool.map(lambda _: generate_report(store, "CASE-REPORT", "reviewer"), range(4)))
    assert len({r.report_id for r in reports}) == 1
    assert len(store.list("CASE-REPORT")) == 1


def test_unknown_context_is_not_verified(saved_case):
    repo, store, _ = saved_case
    with repo._connect() as db:
        record = json.loads(db.execute("SELECT payload FROM comparisons").fetchone()[0])
        record["dataset_compatibility"] = "UNKNOWN"
        db.execute("UPDATE comparisons SET payload=?", (json.dumps(record),))
    persist_graph(repo)
    report = generate_report(store, "CASE-REPORT", "reviewer")
    assert report.status == "INCONCLUSIVE"
    assert report.reproduction_summary[0]["persisted_reproduction_status"] == "VERIFIED"
    assert any(l["code"] == "UNKNOWN_COMPARISON_CONTEXT" for l in report.limitations)


def test_multiple_target_outcomes_are_not_flattened(saved_case):
    repo, store, payload = saved_case
    second = seed(repo, "NOT_REPRODUCED", suffix="-2")
    payload["reproduction_targets"]["candidate_targets"].append(second.model_dump(mode="json"))
    repo.put_research_case("CASE-REPORT", payload, "2026-10-06T00:00:00Z")
    persist_graph(repo)
    report = generate_report(store, "CASE-REPORT", "reviewer")
    assert report.status == "INCONCLUSIVE"
    assert {t["persisted_reproduction_status"] for t in report.reproduction_summary} == {"VERIFIED", "NOT_REPRODUCED"}


def test_absent_source_prevents_complete_assurance(saved_case):
    repo, store, payload = saved_case
    payload["analysis"]["references"] = []
    repo.put_research_case("CASE-REPORT", payload, "2026-10-06T00:00:00Z")
    persist_graph(repo)
    report = generate_report(store, "CASE-REPORT", "reviewer")
    assert report.status == "INCONCLUSIVE"
    assert not report.provenance_summary["valid"]
    assert report.claim_summary[0].associated_source == []


def test_missing_snapshot_is_explicit(saved_case):
    repo, store, _ = saved_case
    with repo._connect() as db:
        db.execute("DELETE FROM graph_snapshots")
    with pytest.raises(ReportInputError, match="Persist a Step 11"):
        generate_report(store, "CASE-REPORT", "reviewer")


def test_persisted_resolution_requires_state_transition_provenance(saved_case):
    from tests.test_evaluator import create_base_data
    repo, store, _ = saved_case
    repo, _, _, iid = create_base_data(repo, target_id="TGT-1")
    investigation = repo.investigations("TGT-1")[0]
    investigation["status"] = "RESOLVED"
    repo.update_investigation(iid, investigation)
    persist_graph(repo)
    report = generate_report(store, "CASE-REPORT", "reviewer")
    assert report.investigation_summary[0]["status"] == "RESOLVED"
    assert report.investigation_summary[0]["final_resolution"] is None
    assert report.status == "INCONCLUSIVE"
    assert any(l["code"] == "MISSING_RESOLUTION_PROVENANCE" for l in report.limitations)


def test_conflicting_published_values_are_not_silently_resolved(saved_case):
    repo, store, payload = saved_case
    payload["analysis"]["experiments"][0]["reported_result"] = 0.91
    repo.put_research_case("CASE-REPORT", payload, "2026-10-06T00:00:00Z")
    persist_graph(repo)
    report = generate_report(store, "CASE-REPORT", "reviewer")
    assert report.status == "INCONCLUSIVE"
    assert any(l["code"] == "CONFLICTING_PUBLISHED_RECORDS" for l in report.limitations)
    assert report.comparison_summary[0]["published_value"] == 0.75
    assert report.experiment_summary[0]["reported_result"] == 0.91


@pytest.mark.parametrize("classification", ["FACT", "AUTHOR_CLAIM", "OBSERVATION", "INFERENCE", "HYPOTHESIS", "UNKNOWN"])
def test_all_epistemic_categories_are_preserved(saved_case, classification):
    repo, store, payload = saved_case
    payload["evidence_items"][0]["classification"] = classification
    repo.put_research_case("CASE-REPORT", payload, "2026-10-06T00:00:00Z")
    persist_graph(repo)
    report = generate_report(store, "CASE-REPORT", "reviewer")
    assert report.evidence_summary[0]["classification"] == classification
    assert report.claim_summary[0].epistemic_status == "AUTHOR_CLAIM"
    if classification == "UNKNOWN":
        assert report.status != "VERIFIED"


def test_conflicting_diagnostics_and_no_false_resolution(saved_case):
    from tests.test_evaluator import create_base_data
    from app.services.execution.evaluator import evaluate_diagnostic

    repo, store, _ = saved_case
    repo, did, hid, iid = create_base_data(repo, target_id="TGT-1")
    diagnostic = repo.load_diagnostic_execution(did)
    for index, outcome in enumerate(("SUPPORTING", "CONTRADICTING")):
        rid, oid, execution_id = f"D-RUN-{index}", f"D-OBS-{index}", f"D-EXEC-{index}"
        baseline = repo.load("runs", "RUN-1")
        baseline["run_id"] = rid
        repo.put("runs", rid, "TGT-1", baseline, "COMPLETED", baseline["timestamp_started"])
        observation = dict(repo.load_observed_result("TGT-1", "RUN-1"), run_id=rid, observed_result_id=oid)
        repo.put_observed_result(oid, "TGT-1", rid, observation, baseline["timestamp_started"])
        record = dict(diagnostic, diagnostic_execution_id=execution_id, outcome=outcome,
                      sandbox_run_id=rid, observed_result_id=oid, baseline_run_id="RUN-1")
        repo.put_diagnostic_execution(execution_id, record["diagnostic_plan_id"], "TGT-1", record, "COMPLETED", record["created_at"])
        evaluate_diagnostic(repo, execution_id)
    persist_graph(repo)
    report = generate_report(store, "CASE-REPORT", "reviewer")
    assert report.status == "INCONCLUSIVE"
    hypothesis = next(h for h in report.hypothesis_summary if h["hypothesis_id"] == hid)
    assert hypothesis["status"] == "INCONCLUSIVE"
    assert hypothesis["supporting_tests"] and hypothesis["contradicting_tests"]
    investigation = next(i for i in report.investigation_summary if i["investigation_id"] == iid)
    assert investigation["status"] == "REQUIRES_HUMAN_REVIEW"
    assert investigation["final_resolution"] is None
    assert any(l["code"] == "CONFLICTING_DIAGNOSTICS" for l in report.limitations)


@pytest.mark.parametrize("status", ["FAILED", "BLOCKED", "CANCELLED"])
def test_failed_blocked_cancelled_diagnostics_remain_visible(saved_case, status):
    from tests.test_evaluator import create_base_data
    repo, store, _ = saved_case
    repo, did, _, _ = create_base_data(repo, target_id="TGT-1")
    diagnostic = repo.load_diagnostic_execution(did)
    diagnostic["status"] = status
    repo.put_diagnostic_execution(did, diagnostic["diagnostic_plan_id"], "TGT-1", diagnostic, status, diagnostic["created_at"])
    persist_graph(repo)
    report = generate_report(store, "CASE-REPORT", "reviewer")
    assert report.diagnostic_summary[0]["execution"]["status"] == status
    assert any(l["code"] == "DIAGNOSTIC_" + status for l in report.limitations)


@pytest.mark.parametrize("change,expected", [("blocked_environment", "BLOCKED"), ("partial_environment", "PARTIALLY_REPRODUCED"), ("missing_excerpt", "PARTIALLY_REPRODUCED"), ("unknown_bibliography", "PARTIALLY_REPRODUCED")])
def test_material_limitations_are_explicit(saved_case, change, expected):
    repo, store, payload = saved_case
    if change.endswith("environment"):
        payload["reproduction_targets"]["candidate_targets"][0]["environment_specification"]["status"] = "BLOCKED" if change.startswith("blocked") else "PARTIALLY_RECONSTRUCTED"
    elif change == "missing_excerpt":
        payload["evidence_items"][0]["excerpt"] = None
    else:
        payload["reference_validation"] = []
    repo.put_research_case("CASE-REPORT", payload, "2026-10-06T00:00:00Z")
    persist_graph(repo)
    report = generate_report(store, "CASE-REPORT", "reviewer")
    assert report.status == expected
    assert report.limitations
    assert not report.unresolved_questions
    assert all(l["source"].startswith(("environments:", "evidence_items:")) for l in report.limitations)


def test_methodology_change_creates_new_version(saved_case, monkeypatch):
    _, store, _ = saved_case
    first = generate_report(store, "CASE-REPORT", "reviewer")
    monkeypatch.setattr("app.services.assurance.METHODOLOGY", "assurance-test-2")
    second = generate_report(store, "CASE-REPORT", "reviewer")
    assert second.report_version == first.report_version + 1
    assert second.report_hash != first.report_hash
    assert second.graph_hash == first.graph_hash


def test_no_default_tolerance_and_complete_source_hashes(saved_case):
    _, store, _ = saved_case
    report = generate_report(store, "CASE-REPORT", "reviewer")
    assert report.comparison_summary[0]["tolerance"] is None
    for key in ("claims:CLM-1", "evidence_items:EVD-1", "sources:REF-1", "targets:TGT-1", "environments:ENV-FIXTURE"):
        assert key in report.source_record_hashes
    assert report.experiment_summary[0]["status"] == "VERIFIED"


def test_corrupted_graph_rejected(saved_case):
    repo, store, _ = saved_case
    with repo._connect() as db:
        record = json.loads(db.execute("SELECT payload FROM graph_snapshots").fetchone()[0])
        record["edges"][0]["target_node_id"] = "absent"
        db.execute("UPDATE graph_snapshots SET payload=?", (json.dumps(record),))
    with pytest.raises(ReportInputError):
        generate_report(store, "CASE-REPORT", "reviewer")


def test_html_escapes_research_text(saved_case):
    repo, store, payload = saved_case
    payload["analysis"]["claims"][0]["claim_text"] = '<script>alert("unsafe")</script>'
    repo.put_research_case("CASE-REPORT", payload, "2026-10-06T00:00:00Z")
    persist_graph(repo)
    html = report_html(generate_report(store, "CASE-REPORT", "reviewer"))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert 'href="#CLAIM_CLM-1"' in html
    assert 'id="CLAIM_CLM-1"' in html
    for section in ("Claim assurance", "Reproduction", "Diagnostics", "Investigations", "Environment", "Limitations", "Provenance"):
        assert section in html


def credential(role="reviewer", exp=None):
    encoded = base64.urlsafe_b64encode(json.dumps({"sub": "tester", "role": role, "exp": exp or time.time()+300}).encode()).decode().rstrip("=")
    return {"Authorization": "Bearer " + encoded + "." + hmac.new(b"test-only-secret", encoded.encode(), hashlib.sha256).hexdigest()}


def test_api_auth_exports_history_and_request_copies(saved_case, monkeypatch):
    _, store, _ = saved_case
    monkeypatch.setenv("AUTH_MODE", "authenticated")
    monkeypatch.setenv("REPROVE_AUTH_SECRET", "test-only-secret")
    app.dependency_overrides[report_store] = lambda: store
    try:
        client = TestClient(app)
        path = "/api/v1/reports/CASE-REPORT/generate"
        assert client.post(path).status_code == 401
        assert client.post(path, headers={"X-User-Role": "admin"}).status_code == 401
        assert client.post(path, headers=credential(exp=1)).status_code == 401
        assert client.post(path, headers=credential("reproduction_approver")).status_code == 403
        assert client.post(path, headers=credential(), json={"status": "VERIFIED"}).status_code == 422
        response = client.post(path, headers=credential())
        assert response.status_code == 200, response.text
        report = response.json()
        rid = report["report_id"]
        assert client.get(f"/api/v1/reports/{rid}").status_code == 401
        assert client.get(f"/api/v1/reports/{rid}/json", headers=credential()).json() == report
        html = client.get(f"/api/v1/reports/{rid}/html", headers=credential())
        assert html.status_code == 200
        assert "default-src 'none'" in html.headers["content-security-policy"]
        assert report["report_hash"] in html.text
        assert len(client.get("/api/v1/research-cases/CASE-REPORT/reports", headers=credential()).json()) == 1
        assert client.get("/api/v1/reports/absent", headers=credential()).status_code == 404
        monkeypatch.setenv("AUTH_MODE", "development")
        assert client.post(path, headers=credential()).status_code == 401
    finally:
        app.dependency_overrides.pop(report_store, None)
