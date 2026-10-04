"""
Self-contained HTML Report Generator.
Generates an interactive, standalone HTML dashboard with embedded search, filters,
and KPI metric cards that opens in any browser with zero server dependencies.
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Any
from src.models.verification import VerificationResult

logger = logging.getLogger(__name__)


def generate_html_dashboard(
    results: List[VerificationResult],
    stats: Dict[str, Any],
    output_html_path: Path,
) -> None:
    """
    Generates standalone interactive HTML dashboard.
    """
    output_html_path.parent.mkdir(parents=True, exist_ok=True)
    records = [r.to_dict() for r in results]
    records_json = json.dumps(records, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Scholarly Reference Validation Report</title>
    <style>
        :root {{
            --primary: #1F497D;
            --accent: #2A6496;
            --bg: #F4F6F9;
            --card-bg: #FFFFFF;
            --text: #333333;
            --border: #E0E0E0;
            --success: #28A745;
            --warning: #FFC107;
            --danger: #DC3545;
            --info: #17A2B8;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
        body {{ background: var(--bg); color: var(--text); padding: 24px; line-height: 1.5; }}
        .header {{ margin-bottom: 24px; }}
        .header h1 {{ color: var(--primary); font-size: 26px; font-weight: 700; }}
        .header p {{ color: #666; font-size: 14px; }}
        
        .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 24px; }}
        .kpi-card {{ background: var(--card-bg); padding: 16px; border-radius: 8px; border: 1px solid var(--border); box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
        .kpi-title {{ font-size: 12px; font-weight: 600; text-transform: uppercase; color: #777; margin-bottom: 6px; }}
        .kpi-value {{ font-size: 24px; font-weight: 700; color: var(--primary); }}
        
        .card {{ background: var(--card-bg); border-radius: 8px; border: 1px solid var(--border); padding: 20px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
        .controls {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; align-items: center; }}
        .controls input, .controls select {{ padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px; font-size: 14px; }}
        .controls input {{ flex: 1; min-width: 240px; }}
        
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }}
        th {{ background: var(--primary); color: #fff; padding: 10px 12px; font-weight: 600; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }}
        tr:hover {{ background: #F8F9FA; }}
        
        .badge {{ display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; text-transform: uppercase; }}
        .badge-recovered {{ background: #D4EDDA; color: #155724; }}
        .badge-wrong {{ background: #F8D7DA; color: #721C24; }}
        .badge-missing {{ background: #FFF3CD; color: #856404; }}
        .badge-review {{ background: #E2E3E5; color: #383D41; }}
        .badge-correct {{ background: #D1ECF1; color: #0C5460; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔬 Scholarly Reference Validation Report</h1>
        <p>Interactive Scientometric Reference Audit & Bibliographic Diagnostics</p>
    </div>

    <div class="kpi-grid">
        <div class="kpi-card"><div class="kpi-title">Documents</div><div class="kpi-value">{stats.get('Documents Analyzed', 0)}</div></div>
        <div class="kpi-card"><div class="kpi-title">Total References</div><div class="kpi-value">{stats.get('References Analyzed', 0)}</div></div>
        <div class="kpi-card"><div class="kpi-title">Resolving DOIs</div><div class="kpi-value">{stats.get('References with Resolving DOI', 0)}</div></div>
        <div class="kpi-card"><div class="kpi-title">DOIs Recovered</div><div class="kpi-value">{stats.get('Missing DOI - Recovered (DOI_RECOVERED)', 0)}</div></div>
        <div class="kpi-card"><div class="kpi-title">Wrong DOI Alerts</div><div class="kpi-value" style="color: #DC3545;">{stats.get('VALID DOI BUT WRONG REFERENCE (VALID_DOI_WRONG_REFERENCE)', 0)}</div></div>
        <div class="kpi-card"><div class="kpi-title">Human Review</div><div class="kpi-value" style="color: #E67E22;">{stats.get('Cases Requiring Human Review', 0)}</div></div>
    </div>

    <div class="card">
        <div class="controls">
            <input type="text" id="searchInput" placeholder="Search references by author, title, DOI, or ID..." onkeyup="filterData()">
            <select id="statusFilter" onchange="filterData()">
                <option value="">All Statuses</option>
                <option value="VALID_CORRECT">VALID_CORRECT</option>
                <option value="SCOPUS_LINKED_NO_DOI">SCOPUS_LINKED_NO_DOI</option>
                <option value="SCOPUS_UNLINKED">SCOPUS_UNLINKED</option>
                <option value="DOI_RECOVERED">DOI_RECOVERED</option>
                <option value="DOI_RECOVERY_UNCERTAIN">DOI_RECOVERY_UNCERTAIN</option>
                <option value="DOI_MISSING">DOI_MISSING</option>
                <option value="VALID_DOI_WRONG_REFERENCE">VALID_DOI_WRONG_REFERENCE</option>
                <option value="ACCESS_RESTRICTED">ACCESS_RESTRICTED</option>
                <option value="BROKEN_URL">BROKEN_URL</option>
            </select>
            <span id="counter" style="font-size: 13px; color: #666;">Showing {len(records)} records</span>
        </div>

        <div style="overflow-x: auto;">
            <table id="dataTable">
                <thead>
                    <tr>
                        <th>Ref ID</th>
                        <th>Source Paper</th>
                        <th>Scopus Linked?</th>
                        <th>Status</th>
                        <th>Confidence</th>
                        <th>Score</th>
                        <th>Normalized DOI</th>
                        <th>Resolved Title</th>
                        <th>Scopus Link / Rationale</th>
                    </tr>
                </thead>
                <tbody id="tableBody"></tbody>
            </table>
        </div>
    </div>

    <script>
        const data = {records_json};

        function getBadgeClass(status) {{
            if (status.includes("RECOVERED") || status.includes("CORRECT")) return "badge-recovered";
            if (status.includes("WRONG") || status.includes("BROKEN")) return "badge-wrong";
            if (status.includes("MISSING") || status.includes("UNLINKED")) return "badge-missing";
            if (status.includes("SCOPUS_LINKED")) return "badge-correct";
            return "badge-review";
        }}

        function renderTable(items) {{
            const tbody = document.getElementById("tableBody");
            tbody.innerHTML = "";
            const slice = items.slice(0, 200);
            for (let r of slice) {{
                const tr = document.createElement("tr");
                const scopusBadge = r.scopus_link_valid ? '<span style="color:green;font-weight:600;">✓ Linked</span>' : '<span style="color:#999;">✗ Unlinked</span>';
                const scopusLinkHtml = (r.scopus_reference_link && r.scopus_reference_link.startsWith('http')) 
                    ? `<a href="${{r.scopus_reference_link}}" target="_blank" style="color:#2A6496;text-decoration:none;">Scopus Record ↗</a>` 
                    : '<span style="color:#888;">Not in Scopus</span>';
                
                tr.innerHTML = `
                    <td><strong>${{r.reference_id}}</strong></td>
                    <td style="max-width:200px;font-size:12px;color:#444;">${{r.source_title ? r.source_title.substring(0, 60) + '...' : ''}}</td>
                    <td>${{scopusBadge}}</td>
                    <td><span class="badge ${{getBadgeClass(r.final_status)}}">${{r.final_status}}</span></td>
                    <td>${{r.confidence}}</td>
                    <td><strong>${{r.composite_score}}</strong></td>
                    <td><code>${{r.normalized_doi || 'None'}}</code></td>
                    <td style="max-width:220px;">${{r.resolved_title || '<span style="color:#999;">N/A</span>'}}</td>
                    <td style="font-size:12px;color:#555;">${{scopusLinkHtml}}<br>${{r.decision_rationale || ''}}</td>
                `;
                tbody.appendChild(tr);
            }}
            document.getElementById("counter").textContent = `Showing ${{slice.length}} of ${{items.length}} records`;
        }}

        function filterData() {{
            const query = document.getElementById("searchInput").value.toLowerCase();
            const status = document.getElementById("statusFilter").value;
            const filtered = data.filter(r => {{
                const matchStatus = !status || r.final_status === status;
                const matchQuery = !query || 
                    (r.raw_reference && r.raw_reference.toLowerCase().includes(query)) ||
                    (r.resolved_title && r.resolved_title.toLowerCase().includes(query)) ||
                    (r.normalized_doi && r.normalized_doi.toLowerCase().includes(query)) ||
                    (r.reference_id && r.reference_id.toLowerCase().includes(query));
                return matchStatus && matchQuery;
            }});
            renderTable(filtered);
        }}

        renderTable(data);
    </script>
</body>
</html>
"""
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    logger.info(f"Generated standalone HTML dashboard at {output_html_path}")

