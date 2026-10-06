"""Self-contained, escaped HTML export of an immutable report; no scripts."""
from html import escape
import json
from urllib.parse import quote

from app.schemas.assurance import AssuranceReport


def report_html(report: AssuranceReport) -> str:
    data = report.model_dump(mode="json")
    node_ids = {n["id"] for n in data["provenance_summary"]["nodes"]}

    def render(value):
        if value is None:
            return '<span class="unknown">Not recorded</span>'
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, list):
            return "<ul>" + "".join("<li>" + render(v) + "</li>" for v in value) + "</ul>" if value else "None recorded"
        if isinstance(value, dict):
            return "<dl>" + "".join("<dt>" + escape(k.replace("_", " ")) + "</dt><dd>" + render(v) + "</dd>" for k, v in value.items()) + "</dl>"
        text = escape(str(value))
        if str(value) in node_ids:
            return '<a href="#' + quote(str(value), safe="") + '">' + text + "</a>"
        return text

    def table(title, rows, columns):
        headers = "".join("<th scope=\"col\">" + escape(label) + "</th>" for _, label in columns)
        body = "".join("<tr>" + "".join("<td>" + render(row.get(key)) + "</td>" for key, _ in columns) + "</tr>" for row in rows)
        return "<section><h2>" + escape(title) + "</h2>" + ("<div class=\"scroll\"><table><thead><tr>" + headers + "</tr></thead><tbody>" + body + "</tbody></table></div>" if rows else "<p>No persisted records.</p>") + "</section>"

    sections = [
        table("Claim assurance", data["claim_summary"], [("claim_text", "Claim"), ("epistemic_status", "Epistemic status"), ("evidence_status", "Evidence support"), ("reproduction_status", "Reproduction status"), ("provenance", "Provenance")]),
        table("Reproduction", data["reproduction_summary"], [("target_id", "Target"), ("experiment_id", "Experiment"), ("published_result", "Published result"), ("observed_results", "Observed results"), ("persisted_reproduction_status", "Step 8 outcome"), ("status", "Assurance status"), ("provenance", "Provenance")]),
        table("Comparisons", data["comparison_summary"], [("comparison_id", "Comparison"), ("published_value", "Published"), ("observed_value", "Observed"), ("absolute_difference", "Difference"), ("tolerance", "Tolerance"), ("tolerance_basis", "Justification"), ("reproduction_status", "Status"), ("provenance", "Provenance")]),
        table("Discrepancies", data["discrepancy_summary"], [("discrepancy_id", "Discrepancy"), ("category", "Category"), ("difference", "Difference"), ("status", "Discrepancy status"), ("investigation_status", "Investigation status"), ("provenance", "Provenance")]),
        table("Hypotheses", data["hypothesis_summary"], [("statement", "Hypothesis"), ("epistemic_status", "Epistemic status"), ("status", "Persisted status"), ("evidence_strength", "Test evidence strength"), ("supporting_tests", "Supporting tests"), ("contradicting_tests", "Contradicting tests"), ("provenance", "Provenance")]),
        table("Diagnostics", data["diagnostic_summary"], [("plan", "Planned change and decision rule"), ("execution", "Execution and outcome"), ("baseline_results", "Baseline via execution run ID"), ("diagnostic_result", "Diagnostic result"), ("tests", "Hypothesis tests"), ("provenance", "Provenance")]),
        table("Investigations", data["investigation_summary"], [("investigation_id", "Investigation"), ("status", "Current status"), ("final_resolution", "Resolution"), ("human_review_required", "Human review required"), ("provenance", "Provenance")]),
        table("Evidence", data["evidence_summary"], [("evidence_id", "Evidence"), ("classification", "Classification"), ("statement", "Statement"), ("validation_status", "Bibliographic validation"), ("provenance", "Provenance")]),
        table("Artifacts", data["artifact_summary"], [("artifact_id", "Artifact"), ("type", "Type"), ("source_url", "Location"), ("availability_status", "Availability"), ("relationship_status", "Verification"), ("hashes", "Staged hashes"), ("usage_in_reproduction", "Recorded usage"), ("provenance", "Provenance")]),
        table("Environment", data["environment_summary"], [("environment_id", "Environment"), ("status", "Reconstruction"), ("python_version", "Python"), ("python_constraint", "Python requirement"), ("operating_system", "OS"), ("dependencies", "Packages and certainty"), ("evidence", "Evidence and certainty"), ("missing_information", "Unknown properties")]),
        table("Limitations", data["limitations"], [("code", "Limitation"), ("detail", "Detail"), ("source", "Source record")]),
        table("Unresolved questions", data["unresolved_questions"], [("question", "Question"), ("source", "Source record")]),
    ]
    provenance = data["provenance_summary"]
    nodes = "".join('<li id="' + quote(n["id"], safe="") + '"><strong>' + escape(n["id"]) + "</strong> — " + escape(n["source_table"]) + "</li>" for n in provenance["nodes"])
    sections.append("<section><h2>Provenance</h2><p>Validation: " + ("PASS" if provenance["valid"] else "INCOMPLETE") + "</p><ul>" + nodes + "</ul>" + render(provenance["issues"]) + "</section>")
    sections.append(table("Graph relationships", provenance["edges"], [("source_node_id", "Source"), ("edge_type", "Relationship"), ("target_node_id", "Destination"), ("provenance", "Persisted field")]))
    sections.append("<section><h2>Complete audit data</h2><details><summary>All report sections, source hashes and state transitions</summary><pre>" + escape(json.dumps(data, indent=2, ensure_ascii=False)) + "</pre></details></section>")
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>REPROVE — Scientific Assurance Report</title>
<style>body{font:16px/1.6 system-ui,sans-serif;color:#172b3a;background:#f5f7fa;margin:0}main{max-width:1200px;margin:auto;padding:32px}header,section{background:white;border:1px solid #dbe3ea;border-radius:8px;padding:24px;margin-bottom:20px}h1{font-size:30px;margin:8px 0}h2{font-size:21px}header small{letter-spacing:2px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #dbe3ea;padding:12px;overflow-wrap:anywhere}th{background:#edf2f7}.scroll{overflow-x:auto}.badge{display:inline-block;border:1px solid #64748b;background:#edf2f7;padding:4px 12px;border-radius:5px;font-weight:700}code,pre{overflow-wrap:anywhere;white-space:pre-wrap;font-size:12px}dt{font-weight:600}dd{margin:0 0 8px}ul{padding-left:18px}a{color:#075985}.unknown{color:#64748b}@media print{body{background:white}main{padding:0}section{break-inside:auto}.scroll{overflow:visible}}</style></head><body><main><header><small>REPROVE</small><h1>Scientific Assurance Report</h1><h2>''' + escape(report.title) + '</h2><p class="badge">' + report.status.value + '</p><p>Research case: ' + escape(report.research_case_id) + " · Report version: " + str(report.report_version) + "</p><p>Report hash: <code>" + report.report_hash + "</code></p><p>Generated: " + escape(report.generated_at.isoformat()) + " · Methodology: " + escape(report.methodology_version) + "</p><p>Graph snapshot: <code>" + escape(report.graph_snapshot_id) + "</code><br>Graph hash: <code>" + escape(report.graph_hash) + "</code></p></header><section><h2>Executive summary</h2>" + render(data["summary"]) + "</section>" + "".join(sections) + "</main></body></html>"
