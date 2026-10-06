# Step 12 — Scientific Assurance Reports

The report is a derived, immutable artifact. Generation uses a consistent read-only
SQLite snapshot and writes only the `assurance_reports` table. It never executes
research code, calls an LLM, downloads evidence, or updates a graph or scientific
record. Source and graph identities, hashes, numerical results, epistemic classes,
hypothesis states and investigation states remain auditable in JSON and HTML.

## API and UI

The report page is `/reports?research_case_id=<case-id>`. It accepts an existing
signed access token, held only in page memory, and supports generation, historical
versions, and authenticated JSON/HTML downloads.

All routes require `AUTH_MODE=authenticated` and the existing HMAC bearer-token
contract (`REPROVE_AUTH_SECRET`, signed subject, role and expiry). Generation
requires `reviewer` or `admin`; reads also allow `reproduction_approver`. These
are global roles in the existing single-workspace authorization model. The
repository has no case-ownership or tenant-membership model.

- `POST /api/v1/reports/{research_case_id}/generate` — accepts no scientific body.
- `GET /api/v1/reports/{report_id}` — immutable report.
- `GET /api/v1/reports/{report_id}/json` — JSON download.
- `GET /api/v1/reports/{report_id}/html` — self-contained, escaped HTML.
- `GET /api/v1/research-cases/{research_case_id}/reports` — version history.

A current persisted Step 11 graph is required. If absent or stale, generation
returns HTTP 409. Refresh the graph via the existing Step 11 graph route first;
report generation itself does not refresh or persist graphs.

## Status methodology `assurance-1.0`

All candidate targets are included conservatively. Original runs determine
reproduction outcomes. Diagnostic sandbox run IDs are excluded from original
reproduction aggregation, including historical diagnostics labeled ORIGINAL by
the execution layer. Their comparisons and outcomes remain visible separately.

Blocked prerequisites yield BLOCKED. Unknown, incomplete or conflicting material
outcomes yield INCONCLUSIVE. Otherwise the original persisted Step 8 statuses
determine the aggregate result. A VERIFIED comparison is necessary but insufficient
for overall VERIFIED: material context and provenance must resolve, claims must
have reproduction coverage, supporting components must be validated, and no
unresolved material investigation or contradiction may remain. Partial supporting
components produce PARTIALLY_REPRODUCED. Per-target persisted status and broader
assurance status are both shown; no comparison, metric, or tolerance is recomputed.

Claims retain AUTHOR_CLAIM status; successful reproduction does not promote them
to FACT. All six evidence categories are preserved. A supported hypothesis does
not make the original reproduction VERIFIED, and an executed diagnostic does
not resolve an investigation. Investigation resolution is copied from persistence.

## Identity, immutability and canonical hashing

Reports use `REPORT-<SHA-256>` identities and monotonically increasing per-case
versions. SHA-256 covers canonical JSON with sorted keys, including source hashes,
graph linkage, schema and methodology versions. The report ID, report hash, version,
generation/creation timestamps and generating principal are excluded. Persisted
scientific identities and timestamps remain source evidence. Repeated generation
of the same snapshot reuses the existing record, including its original author
and generation timestamp. Concurrent writers serialize version allocation through
SQLite `BEGIN IMMEDIATE`. UPDATE, DELETE and replacement attempts are rejected by
database triggers. Readback verifies the canonical report hash.

## Inherited limitations made explicit

Step 10B stores a run ID in `baseline_observed_result_id`. The report preserves
that field verbatim and records a limitation when it does not resolve as an
observation. Diagnostic baseline details use the separate, correctly named
`DiagnosticExecution.baseline_run_id` relationship and label that resolution path.

Step 8 can leave `configuration_compatibility=UNKNOWN` on an otherwise VERIFIED
comparison. Step 12 preserves that comparison verdict but makes the broader target
assurance INCONCLUSIVE until authoritative material context is available. It does
not patch previous stages or infer a missing value.

The standalone HTML includes claim, reproduction, discrepancy, hypothesis,
diagnostic, investigation, evidence, artifact, environment, limitations and
provenance sections. Internal provenance links resolve to snapshot nodes. Complete
source data and hashes appear in the audit appendix. No PDF renderer was added.
