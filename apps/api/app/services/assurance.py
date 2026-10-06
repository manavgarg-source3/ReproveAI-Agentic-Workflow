"""Step 12: deterministic aggregation, with no execution or scientific mutation."""
from contextlib import contextmanager
import json

from app.schemas.assurance import AssuranceReport
from app.schemas.comparison import ComparisonAssessment, ReproductionStatus
from app.schemas.diagnostic import DiagnosticExecution
from app.schemas.execution import ExecutionRecord
from app.schemas.graph import GraphSnapshot
from app.schemas.hypothesis_test import HypothesisTest, StateTransitionEvent
from app.schemas.investigation import DiscrepancyInvestigation, Hypothesis
from app.schemas.research import ObservedResult, EvidenceClassification, ResearchAnalysis, ReproductionTarget, ReproductionPlan, EvidenceItem
from app.services.assurance_store import ReportStore, digest
from app.services.graph_builder import build_graph

METHODOLOGY = "assurance-1.0"
STATUSES = {s.value for s in ReproductionStatus}


class ReportInputError(ValueError):
    pass


def aggregate_status(statuses):
    """Conservative aggregation; details always retain individual outcomes."""
    values = set(statuses)
    if "BLOCKED" in values:
        return "BLOCKED"
    if not values or values - STATUSES or "INCONCLUSIVE" in values:
        return "INCONCLUSIVE"
    if "VERIFIED" in values and "NOT_REPRODUCED" in values:
        return "INCONCLUSIVE"
    if "NOT_REPRODUCED" in values:
        return "NOT_REPRODUCED"
    if "PARTIALLY_REPRODUCED" in values:
        return "PARTIALLY_REPRODUCED"
    return "VERIFIED"


def _rows(db, table, column, ids):
    # Identifiers below are exclusively hard-coded internal table/column names.
    ids = sorted(set(ids))
    if not ids:
        return []
    rows = db.execute(f"SELECT payload FROM {table} WHERE {column} IN ({','.join('?' for _ in ids)})", ids).fetchall()
    return [json.loads(row[0]) for row in rows]


def _validated(records, model, key):
    return sorted((model.model_validate(r).model_dump(mode="json") for r in records), key=lambda r: r[key])


class _GraphReader:
    """Give frozen Step 11 code the same read-only transaction as reporting."""
    def __init__(self, db, data):
        self.db, self.data = db, data

    @contextmanager
    def _connect(self):
        yield self.db

    def list(self, table, target_id):
        return [r for r in self.data[table] if r.get("target_id") == target_id]

    def investigations(self, target_id):
        return self.list("investigations", target_id)

    def diagnostic_executions(self, investigation_id):
        return [r for r in self.data["diagnostic_executions"] if r.get("investigation_id") == investigation_id]


def _graph_content(graph):
    return {
        "research_case_id": graph.research_case_id, "graph_version": graph.graph_version,
        "nodes": sorted([n.model_dump(mode="json", exclude={"created_at"}) for n in graph.nodes], key=lambda n: n["id"]),
        "edges": sorted([e.model_dump(mode="json", exclude={"created_at"}) for e in graph.edges], key=lambda e: e["id"]),
    }


def generate_report(store: ReportStore, case_id: str, principal: str) -> AssuranceReport:
    with store.read_snapshot() as db:
        row = db.execute("SELECT payload FROM research_cases WHERE research_case_id=?", (case_id,)).fetchone()
        if not row:
            raise LookupError("Research case not found")
        case = json.loads(row[0])
        # Validate existing contracts without rewriting the authoritative input.
        ResearchAnalysis.model_validate(case.get("analysis") or {})
        targets = (case.get("reproduction_targets") or {}).get("candidate_targets", [])
        for target in targets:
            ReproductionTarget.model_validate(target)
        for records, key in ((targets, "target_id"), (case["analysis"].get("claims", []), "id"),
                             (case["analysis"].get("experiments", []), "id"),
                             (case["analysis"].get("references", []), "id"),
                             (case.get("evidence_items", []), "evidence_id")):
            if len({r[key] for r in records}) != len(records):
                raise ReportInputError("Duplicate authoritative identity: " + key)
        for plan in case.get("reproduction_plans", []):
            ReproductionPlan.model_validate(plan)
        for evidence in case.get("evidence_items", []):
            EvidenceItem.model_validate(evidence)
        target_ids = [r["target_id"] for r in targets]
        data = {table: _rows(db, table, "target_id", target_ids) for table in (
            "runs", "observed_results", "comparisons", "investigations", "diagnostic_executions",
        )}
        # Select via case-owned investigation identities, never arbitrary UI IDs.
        discrepancy_ids = [i["discrepancy"]["discrepancy_id"] for i in data["investigations"] if i.get("discrepancy")]
        hyp_ids = {h["hypothesis_id"] for i in data["investigations"] for h in i.get("hypotheses", [])}
        hyp_records = _rows(db, "hypotheses", "discrepancy_id", discrepancy_ids)
        hyp_records += _rows(db, "hypotheses", "hypothesis_id", hyp_ids)
        hypotheses = {h["hypothesis_id"]: h for i in data["investigations"] for h in i.get("hypotheses", [])}
        hypotheses.update({h["hypothesis_id"]: h for h in hyp_records})
        data["hypotheses"] = list(hypotheses.values())
        data["hypothesis_tests"] = _rows(db, "hypothesis_tests", "hypothesis_id", hypotheses)
        entity_ids = set(hypotheses) | {i["investigation_id"] for i in data["investigations"]}
        data["state_transitions"] = _rows(db, "state_transitions", "entity_id", entity_ids)
        if target_ids:
            rows = db.execute(f"SELECT staging_id,target_id,artifact_id,sha256,size_bytes FROM artifacts WHERE target_id IN ({','.join('?' for _ in target_ids)})", target_ids).fetchall()
            data["artifact_staging"] = [dict(r) for r in rows]
        else:
            data["artifact_staging"] = []

        row = db.execute("SELECT payload FROM graph_snapshots WHERE research_case_id=? ORDER BY created_at DESC,graph_snapshot_id LIMIT 1", (case_id,)).fetchone()
        if not row:
            raise ReportInputError("Persist a Step 11 graph snapshot before generating the report.")
        graph = GraphSnapshot.model_validate_json(row[0])
        rebuilt = build_graph(case_id, case, _GraphReader(db, data))
        if (graph.research_case_id != case_id or graph.graph_hash != rebuilt.graph_hash
                or _graph_content(graph) != _graph_content(rebuilt)):
            raise ReportInputError("Step 11 graph is stale or inconsistent. Refresh it through Step 11 first.")
        ids = {n.id for n in graph.nodes}
        if (len(ids) != graph.node_count or len(graph.edges) != graph.edge_count
                or len({e.id for e in graph.edges}) != graph.edge_count
                or any(e.source_node_id not in ids or e.target_node_id not in ids for e in graph.edges)):
            raise ReportInputError("Graph contains duplicate, missing, or broken records.")

        raw_hashes = {"research_cases:" + case_id: digest(case)}
        keys = {"runs": "run_id", "observed_results": "observed_result_id", "comparisons": "comparison_id",
                "investigations": "investigation_id", "hypotheses": "hypothesis_id",
                "diagnostic_executions": "diagnostic_execution_id", "hypothesis_tests": "id",
                "state_transitions": "id", "artifact_staging": "staging_id"}
        for table, records in data.items():
            for record in records:
                raw_hashes[table + ":" + record[keys[table]]] = digest(record)
        raw_hashes["graph_snapshots:" + graph.graph_snapshot_id] = digest(_graph_content(graph))
        contracts = {"runs": ExecutionRecord, "observed_results": ObservedResult,
                     "comparisons": ComparisonAssessment, "investigations": DiscrepancyInvestigation,
                     "hypotheses": Hypothesis, "diagnostic_executions": DiagnosticExecution,
                     "hypothesis_tests": HypothesisTest, "state_transitions": StateTransitionEvent}
        for table, model in contracts.items():
            data[table] = _validated(data[table], model, keys[table])
        content = _assemble(case_id, case, data, graph, raw_hashes)
    # The read transaction is closed. Only the new immutable report is written.
    return store.save(content, principal)


def _assemble(case_id, case, data, graph, hashes):
    analysis = case.get("analysis") or {}
    targets = sorted((case.get("reproduction_targets") or {}).get("candidate_targets", []), key=lambda t: t["target_id"])
    targets_by_id = {t["target_id"]: t for t in targets}
    claims = analysis.get("claims") or (case.get("research_case") or {}).get("claims", [])
    claims = sorted(claims, key=lambda c: c.get("id", c.get("claim_id", "")))
    observed = {o["observed_result_id"]: o for o in data["observed_results"]}
    runs = {r["run_id"]: r for r in data["runs"]}
    diagnostics = data["diagnostic_executions"]
    diagnostic_runs = {d["sandbox_run_id"] for d in diagnostics if d.get("sandbox_run_id")}
    tests = data["hypothesis_tests"]
    edges = {(e.source_node_id, e.edge_type.value, e.target_node_id): e.id for e in graph.edges}
    nodes = {n.id for n in graph.nodes}
    issues, limitations, questions, record_links = [], [], [], []
    record_index = []

    def register(kind, identity, record, path):
        reference = kind + ":" + identity
        hashes[reference] = digest(record)
        record_index.append({"id": reference, "path": path, "sha256": hashes[reference]})
        return reference

    for kind, records, key, path in (
        ("claims", claims, "id", "research_cases.analysis.claims"),
        ("experiments", analysis.get("experiments", []), "id", "research_cases.analysis.experiments"),
        ("sources", analysis.get("references", []), "id", "research_cases.analysis.references"),
        ("evidence_items", case.get("evidence_items", []), "evidence_id", "research_cases.evidence_items"),
        ("claim_evidence", case.get("claim_evidence", []), "claim_id", "research_cases.claim_evidence"),
        ("targets", targets, "target_id", "research_cases.reproduction_targets.candidate_targets"),
        ("artifacts", case.get("artifacts", []), "artifact_id", "research_cases.artifacts"),
        ("reproduction_plans", case.get("reproduction_plans", []), "plan_id", "research_cases.reproduction_plans"),
    ):
        for record in records:
            register(kind, record[key], record, path)

    def issue(code, source, detail):
        record = {"code": code, "source": source, "detail": detail}
        if record not in issues:
            issues.append(record)

    def limit(code, source, detail):
        record = {"code": code, "source": source, "detail": detail}
        if record not in limitations:
            limitations.append(record)

    def link(source, kind, destination):
        triple = (source, kind, destination)
        if triple not in edges:
            issue("MISSING_PROVENANCE", source, f"Missing {kind} relationship to {destination}.")
        return edges.get(triple)

    for comparison in data["comparisons"]:
        oid, rid, cid = comparison.get("observed_result_id"), comparison["run_id"], comparison["comparison_id"]
        ob, run = observed.get(oid), runs.get(rid)
        if not ob or not run or ob.get("run_id") != rid or ob.get("target_id") != comparison["target_id"] or run.get("target_id") != comparison["target_id"]:
            issue("INVALID_COMPARISON_SOURCE", "comparisons:" + cid, "Comparison run/observation identity is missing or mismatched.")
        if ob and (ob.get("value") != comparison.get("observed_value") or ob.get("metric_name") != comparison.get("metric_name")):
            issue("CONFLICTING_COMPARISON_SOURCE", "comparisons:" + cid, "Persisted comparison and observation disagree.")
        published = (targets_by_id.get(comparison["target_id"]) or {}).get("published_result") or {}
        if published.get("reported_value") != comparison.get("published_value"):
            issue("CONFLICTING_PUBLISHED_SOURCE", "comparisons:" + cid, "Persisted comparison and target published value disagree.")
        if comparison["reproduction_status"] == "VERIFIED" and (
            comparison["comparison_status"] != "COMPARABLE" or not run or run["status"] != "COMPLETED"
            or not ob or ob["status"] != "EXTRACTED"
        ):
            issue("INVALID_VERIFIED_COMPARISON", "comparisons:" + cid, "VERIFIED comparison lacks completed, extracted, comparable source evidence.")
        link("OBSERVED_RESULT_" + str(oid), "COMPARED_WITH", "COMPARISON_" + cid)
        link("EXECUTION_" + rid, "PRODUCED", "OBSERVED_RESULT_" + str(oid))
        link("REPRODUCTION_TARGET_" + comparison["target_id"], "EXECUTED_AS", "EXECUTION_" + rid)
        for text in comparison["limitations"] + comparison["warnings"]:
            limit("COMPARISON_LIMITATION", "comparisons:" + cid, text)

    for diagnostic in diagnostics:
        did = diagnostic["diagnostic_execution_id"]
        inv = next((i for i in data["investigations"] if i["investigation_id"] == diagnostic["investigation_id"]), None)
        if not inv or inv["target_id"] != diagnostic["target_id"]:
            issue("INVALID_DIAGNOSTIC_INVESTIGATION", "diagnostic_executions:" + did, "Diagnostic investigation does not resolve within its target.")
        link("DIAGNOSTIC_PLAN_" + diagnostic["diagnostic_plan_id"], "EXECUTED_DIAGNOSTIC", "DIAGNOSTIC_EXECUTION_" + did)
        oid = diagnostic.get("observed_result_id")
        if oid:
            link("DIAGNOSTIC_EXECUTION_" + did, "PRODUCED", "OBSERVED_RESULT_" + oid)
            ob = observed.get(oid)
            if not ob or ob.get("run_id") != diagnostic.get("sandbox_run_id"):
                issue("INVALID_DIAGNOSTIC_SOURCE", "diagnostic_executions:" + did, "Diagnostic observation does not resolve to its sandbox run.")
        elif diagnostic["status"] == "COMPLETED":
            issue("MISSING_DIAGNOSTIC_RESULT", "diagnostic_executions:" + did, "Completed diagnostic has no persisted observed-result ID.")
        if diagnostic["status"] in {"FAILED", "BLOCKED", "CANCELLED", "INVALID"}:
            limit("DIAGNOSTIC_" + diagnostic["status"], "diagnostic_executions:" + did, diagnostic.get("decision_reason") or diagnostic["status"])
    for test in tests:
        diagnostic = next((d for d in diagnostics if d["diagnostic_execution_id"] == test["diagnostic_execution_id"]), None)
        if not diagnostic or any(test.get(field) != diagnostic.get(field) for field in ("investigation_id", "diagnostic_plan_id")) or test.get("diagnostic_observed_result_id") != diagnostic.get("observed_result_id"):
            issue("INVALID_TEST_SOURCE", "hypothesis_tests:" + test["id"], "Hypothesis test context does not match its persisted diagnostic execution.")
        plan = next((p for i in data["investigations"] for p in i["diagnostic_plans"] if p["diagnostic_plan_id"] == test["diagnostic_plan_id"]), None)
        if not plan or plan["hypothesis_id"] != test["hypothesis_id"]:
            issue("INVALID_TEST_HYPOTHESIS", "hypothesis_tests:" + test["id"], "Hypothesis test does not match its authoritative diagnostic plan.")
        link("DIAGNOSTIC_EXECUTION_" + test["diagnostic_execution_id"], "TEST_RESULT", "HYPOTHESIS_TEST_" + test["id"])
        link("HYPOTHESIS_" + test["hypothesis_id"], "TESTED_BY", "HYPOTHESIS_TEST_" + test["id"])
        if test.get("diagnostic_observed_result_id"):
            link("OBSERVED_RESULT_" + test["diagnostic_observed_result_id"], "TEST_RESULT", "HYPOTHESIS_TEST_" + test["id"])
        if test.get("baseline_observed_result_id") not in observed:
            limit("HISTORICAL_BASELINE_REFERENCE", "hypothesis_tests:" + test["id"],
                  "baseline_observed_result_id does not resolve as an observation ID; the historical value is preserved, not reinterpreted.")

    references = {r["id"]: r for r in analysis.get("references", [])}
    validations = {r["reference_id"]: r for r in case.get("reference_validation", [])}
    evidence = []
    for item in sorted(case.get("evidence_items", []), key=lambda e: e["evidence_id"]):
        classification = item.get("classification", "UNKNOWN")
        EvidenceClassification(classification)
        eid, source_id = item["evidence_id"], item.get("reference_id")
        if "EVIDENCE_" + eid not in nodes:
            issue("MISSING_EVIDENCE_NODE", "evidence_items:" + eid, "Evidence is absent from the graph.")
        if source_id:
            link("EVIDENCE_" + eid, "DERIVED_FROM", "SOURCE_" + source_id)
        else:
            issue("MISSING_SOURCE", "evidence_items:" + eid, "Evidence has no authoritative reference ID.")
        evidence.append({**item, "classification": classification, "statement": item.get("excerpt"),
                         "source_id": source_id, "validation_status": validations.get(source_id, {}).get("status", "UNKNOWN"),
                         "provenance": ["EVIDENCE_" + eid] + (["SOURCE_" + source_id] if source_id in references else [])})
        if item.get("evidence_type") == "UNAVAILABLE" or not item.get("excerpt"):
            limit("SOURCE_TEXT_UNAVAILABLE", "evidence_items:" + eid, "No inspectable source text is persisted for this evidence item.")
        if classification == "UNKNOWN":
            limit("UNKNOWN_EVIDENCE_CLASSIFICATION", "evidence_items:" + eid, "The evidence classification is UNKNOWN.")
        if validations.get(source_id, {}).get("status", "UNKNOWN") not in {"VALID_CORRECT", "VALID_REDIRECT_CORRECT", "DOI_RECOVERED", "SCOPUS_LINKED_NO_DOI"}:
            limit("SOURCE_VALIDATION", "evidence_items:" + eid, "Persisted bibliographic validation is " + validations.get(source_id, {}).get("status", "UNKNOWN") + ".")

    reproduction = []
    reproduction_plans = {p["plan_id"]: p for p in case.get("reproduction_plans", [])}
    for target in targets:
        tid = target["target_id"]
        experiment = next((e for e in analysis.get("experiments", []) if e["id"] == target["experiment_id"]), None)
        published = target.get("published_result") or {}
        claim = next((c for c in claims if c.get("id") == published.get("source_claim_id")), None)
        for record, value_key, label in ((experiment, "reported_result", "experiment"), (claim, "reported_value", "claim")):
            if record and record.get(value_key) is not None and record[value_key] != published.get("reported_value"):
                issue("CONFLICTING_PUBLISHED_RECORDS", "targets:" + tid, "Target published value differs from its explicitly associated " + label + " record.")
        if target.get("plan_id") not in reproduction_plans:
            limit("MISSING_REPRODUCTION_PLAN", "targets:" + tid, "The referenced reproduction-plan body is not persisted in this research case.")
        else:
            record_links.append({"source": "targets:" + tid, "field": "plan_id", "target": "reproduction_plans:" + target["plan_id"]})
        target_runs = [r for r in data["runs"] if r["target_id"] == tid and r["run_id"] not in diagnostic_runs and r.get("execution_type") == "ORIGINAL"]
        original_ids = {r["run_id"] for r in target_runs}
        comparisons = [c for c in data["comparisons"] if c["target_id"] == tid and c["run_id"] in original_ids]
        statuses = [c["reproduction_status"] for c in comparisons]
        if target.get("readiness_status") == "BLOCKED" or any(r["status"] == "BLOCKED" for r in target_runs):
            statuses.append("BLOCKED")
        elif not target_runs or any(r["status"] != "COMPLETED" for r in target_runs):
            statuses.append("INCONCLUSIVE")
        if any(r["run_id"] not in {c["run_id"] for c in comparisons} for r in target_runs):
            statuses.append("INCONCLUSIVE")
        persisted_status = aggregate_status(statuses)
        target_status = persisted_status
        context_fields = ["metric_compatibility", "dataset_compatibility", "split_compatibility", "model_compatibility", "checkpoint_compatibility", "configuration_compatibility", "evaluation_protocol_compatibility"]
        # Step 8 currently leaves configuration UNKNOWN, even when other context
        # matches. Preserve its verdict but do not call the broader assurance complete.
        if target_status == "VERIFIED" and any(c.get(k, "UNKNOWN") == "UNKNOWN" for c in comparisons for k in context_fields):
            target_status = "INCONCLUSIVE"
            limit("UNKNOWN_COMPARISON_CONTEXT", "targets:" + tid, "At least one persisted comparison context dimension is UNKNOWN.")
        elif target_status == "VERIFIED" and any(c.get(k) in {"PARTIAL_MATCH", "MISMATCH"} for c in comparisons for k in context_fields):
            target_status = "PARTIALLY_REPRODUCED" if not any(c.get(k) == "MISMATCH" for c in comparisons for k in context_fields) else "INCONCLUSIVE"
        link("EXPERIMENT_" + target["experiment_id"], "MAPS_TO", "REPRODUCTION_TARGET_" + tid)
        if target.get("code_artifact_id"):
            link("REPRODUCTION_TARGET_" + tid, "USES_ARTIFACT", "ARTIFACT_" + target["code_artifact_id"])
        else:
            issue("MISSING_ARTIFACT_REFERENCE", "targets:" + tid, "Target has no code-artifact identity.")
        reproduction.append({"target_id": tid, "experiment_id": target["experiment_id"],
                             "selected": target.get("selected", False), "dataset": target.get("dataset"),
                             "model": target.get("model"), "checkpoint": target.get("checkpoint"),
                             "metric": target.get("metric"), "published_result": target.get("published_result"),
                             "execution_status": [{key: r.get(key) for key in (
                                 "run_id", "status", "execution_type", "artifact_hash", "environment_id",
                                 "failure_code", "failure_reason", "timestamp_started", "timestamp_finished", "runtime_seconds",
                             )} for r in target_runs],
                             "observed_results": [o for o in data["observed_results"] if o.get("run_id") in original_ids],
                             "comparison_ids": [c["comparison_id"] for c in comparisons],
                             "persisted_reproduction_status": persisted_status, "status": target_status,
                             "provenance": ["REPRODUCTION_TARGET_" + tid] + ["COMPARISON_" + c["comparison_id"] for c in comparisons]})
        for missing in target.get("missing_requirements", []):
            limit("MISSING_REQUIREMENT", "targets:" + tid, missing)
        if persisted_status in {"BLOCKED", "INCONCLUSIVE"}:
            limit("REPRODUCTION_" + persisted_status, "targets:" + tid, "Persisted execution/comparison coverage is " + persisted_status + ".")

    by_target = {t["target_id"]: t for t in reproduction}
    claim_summary = []
    assessments = {a["claim_id"]: a for a in case.get("claim_evidence", [])}
    for claim in claims:
        cid = claim.get("id", claim.get("claim_id"))
        matching = [t for t in targets if (t.get("published_result") or {}).get("source_claim_id") == cid]
        items = [e for e in evidence if e.get("claim_id") == cid]
        assessment = assessments.get(cid, {})
        support_status = assessment.get("support_status", "UNKNOWN")
        for eid in assessment.get("evidence_ids", []):
            if eid not in {e["evidence_id"] for e in items}:
                issue("INVALID_CLAIM_EVIDENCE", "claims:" + cid, "Assessment references absent or differently owned evidence " + eid)
            if support_status in {"SUPPORTED", "PARTIALLY_SUPPORTED"}:
                link("CLAIM_" + cid, "SUPPORTED_BY" if support_status == "SUPPORTED" else "PARTIALLY_SUPPORTED_BY", "EVIDENCE_" + eid)
        if support_status == "SUPPORTED" and not assessment.get("evidence_ids"):
            issue("EMPTY_SUPPORT_ASSESSMENT", "claims:" + cid, "SUPPORTED assessment has no evidence IDs.")
        for target in matching:
            link("CLAIM_" + cid, "MAPS_TO", "EXPERIMENT_" + target["experiment_id"])
        matching_ids = {t["target_id"] for t in matching}
        related = [c for c in data["comparisons"] if c["target_id"] in matching_ids and c["run_id"] not in diagnostic_runs]
        claim_summary.append({"claim_id": cid, "claim_text": claim.get("claim_text", claim.get("description", "")),
                              "claim_type": claim.get("claim_type", "UNKNOWN"),
                              "epistemic_status": claim.get("epistemic_status", "AUTHOR_CLAIM"),
                              "evidence_status": support_status,
                              "reproduction_status": aggregate_status([by_target[t["target_id"]]["status"] for t in matching]),
                              "associated_evidence": [e["evidence_id"] for e in items],
                              "associated_source": sorted({e["source_id"] for e in items if e["source_id"] in references}),
                              "associated_experiment": sorted({t["experiment_id"] for t in matching}),
                              "supporting_observations": [c["observed_result_id"] for c in related if c["reproduction_status"] == "VERIFIED" and c.get("observed_result_id")],
                              "contradictory_observations": [c["observed_result_id"] for c in related if c["reproduction_status"] == "NOT_REPRODUCED" and c.get("observed_result_id")],
                              "provenance": ["CLAIM_" + cid] + ["EVIDENCE_" + e["evidence_id"] for e in items]})
        if not matching or support_status != "SUPPORTED":
            limit("CLAIM_COVERAGE", "claims:" + cid, "Claim evidence status: " + support_status + "; associated reproduction targets: " + str(len(matching)) + ".")
        for question in assessment.get("unresolved_questions", []):
            questions.append({"source": "claim_evidence:" + cid, "question": question})

    environments = {e["environment_id"]: e for e in case.get("environment_specifications", [])}
    for target in targets:
        if target.get("environment_specification"):
            e = target["environment_specification"]
            environments.setdefault(e["environment_id"], e)
        eid = target.get("environment_id")
        if eid not in environments:
            issue("MISSING_ENVIRONMENT", "targets:" + target["target_id"], "Target environment does not resolve to a persisted specification.")
        else:
            record_links.append({"source": "targets:" + target["target_id"], "field": "environment_id", "target": "environments:" + eid})
    for eid, environment in environments.items():
        register("environments", eid, environment, "research_cases.environment_specifications or reproduction_targets.environment_specification")
        if environment.get("status") != "RECONSTRUCTED":
            limit("ENVIRONMENT_" + environment.get("status", "UNKNOWN"), "environments:" + eid, "Environment reconstruction is " + environment.get("status", "UNKNOWN") + ".")
        for text in environment.get("missing_information", []):
            limit("ENVIRONMENT_MISSING_INFORMATION", "environments:" + eid, text)
        for item in environment.get("evidence", []):
            if item.get("certainty") != "EXPLICIT":
                limit("ENVIRONMENT_CERTAINTY", "environments:" + eid, item)
        if environment.get("conflict_detected"):
            issue("ENVIRONMENT_CONFLICT", "environments:" + eid, "Persisted environment reconstruction reports a conflict.")

    artifacts = []
    for artifact in sorted(case.get("artifacts", []), key=lambda a: a.get("artifact_id", a.get("id", ""))):
        aid = artifact.get("artifact_id", artifact.get("id"))
        usage = [r for r in data["runs"] if r.get("artifact_id") == aid]
        artifacts.append({**artifact, "hashes": sorted({r["sha256"] for r in data["artifact_staging"] if r["artifact_id"] == aid}),
                          "usage_in_reproduction": [{"run_id": r["run_id"], "execution_status": r["status"], "artifact_hash": r.get("artifact_hash")} for r in usage],
                          "provenance": ["ARTIFACT_" + aid]})
        if artifact.get("availability_status", "UNKNOWN") not in {"FOUND", "VERIFIED"}:
            limit("ARTIFACT_AVAILABILITY", "artifacts:" + aid, artifact.get("availability_status", "UNKNOWN"))

    discrepancies, investigations, plans = [], [], {}
    for inv in data["investigations"]:
        iid = inv["investigation_id"]
        if inv.get("discrepancy"):
            discrepancy = inv["discrepancy"]
            did = discrepancy["discrepancy_id"]
            register("discrepancies", did, discrepancy, "investigations.discrepancy")
            discrepancies.append({**discrepancy, "investigation_id": iid, "investigation_status": inv["status"], "provenance": ["DISCREPANCY_" + did]})
            link("COMPARISON_" + discrepancy["comparison_id"], "GENERATED_DISCREPANCY", "DISCREPANCY_" + did)
            link("DISCREPANCY_" + did, "INVESTIGATES", "INVESTIGATION_" + iid)
        for plan in inv["diagnostic_plans"]:
            register("diagnostic_plans", plan["diagnostic_plan_id"], plan, "investigations.diagnostic_plans")
            plans[plan["diagnostic_plan_id"]] = plan
            link("HYPOTHESIS_" + plan["hypothesis_id"], "HAS_DIAGNOSTIC_PLAN", "DIAGNOSTIC_PLAN_" + plan["diagnostic_plan_id"])
            if inv["status"] != "RESOLVED":
                questions.append({"source": "diagnostic_plans:" + plan["diagnostic_plan_id"], "question": plan["question"]})
        resolution_supported = any(t["entity_type"] == "INVESTIGATION" and t["entity_id"] == iid
                                   and t["new_state"] == "RESOLVED" and t.get("triggering_test_id") in {test["id"] for test in tests if test["investigation_id"] == iid}
                                   for t in data["state_transitions"])
        if inv["status"] == "RESOLVED" and not resolution_supported:
            issue("MISSING_RESOLUTION_PROVENANCE", "investigations:" + iid, "Persisted RESOLVED status has no linked Step 10B test/state-transition evidence.")
        investigations.append({**inv, "final_resolution": "RESOLVED" if inv["status"] == "RESOLVED" and resolution_supported else None,
                               "provenance": ["INVESTIGATION_" + iid]})
        for embedded in inv["hypotheses"]:
            current = next((h for h in data["hypotheses"] if h["hypothesis_id"] == embedded["hypothesis_id"]), None)
            if current and current["status"] != embedded["status"]:
                issue("CONFLICTING_HYPOTHESIS_STATE", "investigations:" + iid, "Embedded and authoritative hypothesis statuses disagree for " + embedded["hypothesis_id"] + ".")
        if inv["human_review_required"]:
            limit("HUMAN_REVIEW_REQUIRED", "investigations:" + iid, "The persisted investigation requires human review.")
        for text in inv["limitations"]:
            limit("INVESTIGATION_LIMITATION", "investigations:" + iid, text)

    hypothesis_summary = []
    conflicting_diagnostics = False
    for hypothesis in data["hypotheses"]:
        hid = hypothesis["hypothesis_id"]
        related_tests = [t for t in tests if t["hypothesis_id"] == hid]
        outcomes = {t["diagnostic_outcome"] for t in related_tests}
        conflict = {"SUPPORTING", "CONTRADICTING"} <= outcomes
        conflicting_diagnostics |= conflict
        if conflict:
            limit("CONFLICTING_DIAGNOSTICS", "hypotheses:" + hid, "Persisted tests include supporting and contradicting outcomes.")
        hypothesis_summary.append({**hypothesis, "epistemic_status": "HYPOTHESIS",
                                   "evidence_strength": [{"test_id": t["id"], "strength": t["evidence_strength"]} for t in related_tests],
                                   "supporting_tests": [t["id"] for t in related_tests if t["diagnostic_outcome"] == "SUPPORTING"],
                                   "contradicting_tests": [t["id"] for t in related_tests if t["diagnostic_outcome"] == "CONTRADICTING"],
                                   "inconclusive_tests": [t["id"] for t in related_tests if t["diagnostic_outcome"] in {"INCONCLUSIVE", "BLOCKED", "UNKNOWN"}],
                                   "investigations": [i["investigation_id"] for i in investigations if hid in {h["hypothesis_id"] for h in i["hypotheses"]}],
                                   "human_review_required": any(i["human_review_required"] for i in investigations if hid in {h["hypothesis_id"] for h in i["hypotheses"]}),
                                   "provenance": ["HYPOTHESIS_" + hid]})

    diagnostic_summary = []
    for pid, plan in sorted(plans.items()):
        related = [d for d in diagnostics if d["diagnostic_plan_id"] == pid]
        for diagnostic in related or [None]:
            diagnostic_summary.append({"plan": plan, "execution": diagnostic,
                                       "baseline_results": [o for o in observed.values() if diagnostic and o["run_id"] == diagnostic["baseline_run_id"]],
                                       "baseline_resolution_field": "diagnostic_executions.baseline_run_id -> observed_results.run_id",
                                       "diagnostic_result": observed.get(diagnostic.get("observed_result_id")) if diagnostic else None,
                                       "tests": [t for t in tests if diagnostic and t["diagnostic_execution_id"] == diagnostic["diagnostic_execution_id"]],
                                       "provenance": ["DIAGNOSTIC_PLAN_" + pid] + (["DIAGNOSTIC_EXECUTION_" + diagnostic["diagnostic_execution_id"]] if diagnostic else [])})
    for diagnostic in diagnostics:
        if diagnostic["diagnostic_plan_id"] not in plans:
            diagnostic_summary.append({"plan": None, "execution": diagnostic, "provenance": ["DIAGNOSTIC_EXECUTION_" + diagnostic["diagnostic_execution_id"]]})

    status = aggregate_status([t["status"] for t in reproduction])
    required_env_ids = {t.get("environment_id") for t in targets}
    if any(e.get("status") == "BLOCKED" for eid, e in environments.items() if eid in required_env_ids):
        status = "BLOCKED"
    if status != "BLOCKED" and (issues or conflicting_diagnostics):
        status = "INCONCLUSIVE"
    if status == "VERIFIED":
        if not claims or any(c["reproduction_status"] == "INCONCLUSIVE" for c in claim_summary) or any(e["classification"] == "UNKNOWN" for e in evidence):
            status = "INCONCLUSIVE"
        elif any(i["status"] not in {"RESOLVED", "NO_DISCREPANCY"} for i in investigations):
            status = "INCONCLUSIVE"
        elif (any(c["evidence_status"] != "SUPPORTED" for c in claim_summary)
              or any(e.get("status") != "RECONSTRUCTED" for e in environments.values())
              or any(a.get("availability_status") not in {"FOUND", "VERIFIED"} for a in artifacts)
              or any(i["human_review_required"] for i in investigations)
              or any(l["code"] in {"SOURCE_TEXT_UNAVAILABLE", "SOURCE_VALIDATION", "ENVIRONMENT_CERTAINTY", "ENVIRONMENT_MISSING_INFORMATION", "MISSING_REPRODUCTION_PLAN"} for l in limitations)):
            status = "PARTIALLY_REPRODUCED"
    limitations.extend(issues)

    comparisons = []
    for comparison in data["comparisons"]:
        target = targets_by_id[comparison["target_id"]]
        comparisons.append({**comparison, "dataset": target.get("dataset"), "model": target.get("model"),
                            "checkpoint": target.get("checkpoint"), "evaluation_protocol": target.get("evaluation_protocol"),
                            "is_diagnostic": comparison["run_id"] in diagnostic_runs,
                            "provenance": ["COMPARISON_" + comparison["comparison_id"], "OBSERVED_RESULT_" + str(comparison.get("observed_result_id"))]})

    experiment_summary = [{**experiment, "epistemic_status": "AUTHOR_CLAIM",
                           "target_ids": [t["target_id"] for t in reproduction if t["experiment_id"] == experiment["id"]],
                           "status": aggregate_status([t["status"] for t in reproduction if t["experiment_id"] == experiment["id"]]),
                           "provenance": ["EXPERIMENT_" + experiment["id"]]} for experiment in analysis.get("experiments", [])]
    return dict(research_case_id=case_id, schema_version="1.0", methodology_version=METHODOLOGY,
                status=status, title=(analysis.get("paper") or {}).get("title") or "Scientific Assurance Report",
                graph_snapshot_id=graph.graph_snapshot_id, graph_version=graph.graph_version, graph_hash=graph.graph_hash,
                summary={"examined": {"claims": len(claims), "experiments": len(analysis.get("experiments", [])), "targets": len(targets)},
                         "conclusion": "Overall assurance is " + status + " under the persisted reproduction conditions.",
                         "scope": "Reproduction assurance is not a determination of scientific truth. Diagnostic outcomes do not replace original reproduction comparisons.",
                         "reproduced": [{"target_id": t["target_id"], "persisted_status": t["persisted_reproduction_status"], "assurance_status": t["status"]} for t in reproduction],
                         "major_limitations": limitations[:5],
                         "status_rule": "Blocked prerequisites first; unknown/conflicting outcomes or missing provenance are inconclusive; original target comparisons determine reproduction outcomes; incomplete supporting components prevent full assurance.",
                         "artifact_counts": {key: sum(a.get("availability_status") in vals for a in artifacts) for key, vals in {"available": {"FOUND", "VERIFIED"}, "unavailable": {"MISSING", "INACCESSIBLE"}, "partial": {"PARTIAL", "AMBIGUOUS"}, "unknown": {None, "UNKNOWN"}}.items()}},
                claim_summary=claim_summary, evidence_summary=evidence,
                source_summary=[{**r, "validation": validations.get(r["id"]), "provenance": ["SOURCE_" + r["id"]]} for r in sorted(references.values(), key=lambda r: r["id"])],
                experiment_summary=experiment_summary, method_summary=analysis.get("methods", []),
                artifact_summary=artifacts, environment_summary=[environments[k] for k in sorted(environments)],
                reproduction_summary=reproduction, reproduction_plan_summary=case.get("reproduction_plans", []),
                comparison_summary=comparisons, discrepancy_summary=discrepancies, investigation_summary=investigations,
                hypothesis_summary=hypothesis_summary, diagnostic_summary=diagnostic_summary,
                hypothesis_test_summary=tests, state_transition_summary=data["state_transitions"],
                limitations=sorted(limitations, key=lambda r: (r["source"], r["code"], str(r["detail"]))),
                unresolved_questions=sorted(questions, key=lambda r: (r["source"], r["question"])),
                provenance_summary={"valid": not issues, "issues": issues, "record_links": record_links, "source_records": sorted(record_index, key=lambda r: r["id"]),
                                    "nodes": [{"id": n.id, "node_type": n.node_type.value, "entity_id": n.entity_id, "source_table": n.source_table, "source_hash": n.source_hash} for n in graph.nodes],
                                    "edges": [e.model_dump(mode="json", exclude={"created_at"}) for e in graph.edges]},
                source_record_hashes=dict(sorted(hashes.items())), immutable=True)
