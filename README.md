# REPROVE

REPROVE currently provides one traceable vertical slice: upload a PDF, extract its text, analyze it with Google Gemini, validate a strict research-analysis schema, validate its references with the existing scientometric engine, compare citation-backed claims with bounded source evidence, and render the result. There is no agent framework, application database, queue, or container runtime yet; the reused engine retains its own local provider cache.

For a file-by-file explanation, function responsibilities, architectural decisions, and dated change history, see [`IMPLEMENTATION_LOG.md`](./IMPLEMENTATION_LOG.md). This living document is updated with every implementation change.

## Repository

```text
apps/
  api/   FastAPI, Pydantic, and pypdf
  web/   Next.js, TypeScript, and Tailwind CSS
```

## Run the API

Python 3.11 or newer is recommended.

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add your Gemini API key to .env. Never commit this file.
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000`. Its health endpoint is `GET /health`, interactive docs are at `http://localhost:8000/docs`, and paper analysis is:

```text
POST /api/v1/analyze-paper
Content-Type: multipart/form-data
field: file
```

Only PDFs up to 25 MB are accepted. Image-only/scanned PDFs need OCR, which is outside Step 1.

Required analyzer configuration:

```dotenv
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-3.8-flash
MAX_ANALYSIS_CHARACTERS=120000
GEMINI_MAX_INPUT_CHARS=45000
GEMINI_CHUNK_CHARS=40000
GEMINI_CHUNK_OVERLAP_CHARS=500
GEMINI_TIMEOUT_SECONDS=120
```

`GEMINI_MODEL` is configurable because model availability and capacity can vary. The full extracted document remains available inside the request for deterministic reference, citation-evidence, and artifact stages. The main Gemini analyzer detects scientific sections, excludes the bibliography, prioritizes useful sections, and bounds selected context with `MAX_ANALYSIS_CHARACTERS`. It creates paragraph-aware chunks no larger than the per-call limit, analyzes each chunk, and deterministically merges conservative duplicates. Poorly structured papers use an explicit bounded full-text fallback. Character limits are operational bounds, not token counts.

The response includes an optional `analysis_context` diagnostic block with full extracted size, detected/selected section information, selected size, Gemini input size, chunk count, and fallback state. It never returns the selected paper text.

## Scientometric Engine Integration

The existing engine is checked into this workspace at `Scientometric-Audit-Studio-main/`. The Step 1C brief referred to `engines/scientometric/`, but that path is not present, so the engine was kept in its actual location and was not moved, copied, or rewritten.

REPROVE accesses it only through `apps/api/app/services/scholarly/scientometric_adapter.py`. The adapter translates the existing REPROVE `Reference` schema to the engine's `ParsedReference`, invokes `ReferenceValidator`, and translates `VerificationResult` into the small Pydantic `ReferenceValidation` response model.

Currently reused engine capabilities:

- DOI extraction and normalization;
- DOI.org resolution;
- Crossref metadata lookup and bibliographic search;
- OpenAlex lookup fallback;
- optional Scopus lookup when configured;
- citation parsing;
- title, author, journal, year, volume, and page matching;
- composite scoring and existing validation statuses such as `VALID_DOI_WRONG_REFERENCE`;
- the engine's SQLite HTTP-response cache.

Provider configuration:

```dotenv
# Optional polite-pool contact information
CROSSREF_MAILTO=you@example.com
OPENALEX_EMAIL=you@example.com

# Optional paid provider; Crossref/OpenAlex do not require it
ELSEVIER_API_KEY=

# Optional engine location override
SCIENTOMETRIC_ENGINE_PATH=
```

One reference failure is isolated and returned as `SOURCE_UNAVAILABLE` or `ERROR`; it does not fail the paper analysis. Identical reference inputs are reused in-process, and the engine cache avoids repeated external requests.

This integration validates bibliographic identity and metadata only. It does not validate scientific claims, classify citation support, reproduce experiments, execute code, or establish scientific truth.

## Claim Evidence Validation

Step 2 adds a limited, request-scoped citation-support assessment to the existing upload endpoint. It does not add a second product flow or persist evidence.

The deterministic part of the pipeline:

1. uses the preserved scientometric engine to separate the manuscript body and extract in-text citation contexts;
2. conservatively maps a claim to numeric or author-year references only when the actual paper context is sufficiently similar;
3. reuses Step 1C bibliographic validation and normalized DOI results;
4. requests bounded abstracts from Crossref first and OpenAlex second; and
5. explicitly records missing citations, metadata-only records, unavailable text, source locators, and human-review requirements.

When inspectable text exists, Gemini receives only the author claim, actual citation context, source identity, and bounded source excerpt. It returns a schema-validated `SUPPORTED`, `PARTIALLY_SUPPORTED`, `NOT_SUPPORTED`, `CONTRADICTED`, `UNCLEAR`, or `SOURCE_UNAVAILABLE` assessment. The prompt prohibits using source titles or bibliographic metadata as evidence, inventing excerpts, or claiming scientific truth. Missing source text is never converted into contradiction or lack of support.

`MAX_SOURCE_EVIDENCE_CHARACTERS` controls the maximum abstract/excerpt size supplied for one source and defaults to `6000`. REPROVE does not crawl publisher sites, bypass paywalls, retrieve unlimited full text, or use embeddings/vector search.

The frontend's **Claim Evidence** section displays the author claim, citation marker and context, reference, provider, bounded excerpt, graded support status, explanation, unresolved questions, and review signal. A supported citation relationship means only that the available cited text supports the statement; it does not mean the scientific claim is true or reproduced.

## Artifact Discovery

Step 3A adds request-scoped discovery and limited identity verification for computational artifacts. It searches the extracted paper text first and does not conduct broad web searches.

Supported artifact types are `CODE`, `DATASET`, `MODEL`, `CHECKPOINT`, `CONFIG`, `DEPENDENCY`, `CONTAINER`, `SUPPLEMENTARY`, and `EXECUTION_SCRIPT`.

Discovery currently uses:

- explicit HTTP(S) URLs and repository mentions in the paper;
- public GitHub and GitLab metadata for explicitly linked repositories;
- bounded README excerpts, root file names, license, default branch, and latest visible commit metadata;
- visible dependency/configuration/container/execution filenames;
- explicit experiment dataset and model fields when no exact public source/version can be established; and
- explicit supplementary, model, checkpoint, and dataset links.

Repository URL variants such as a trailing slash or `.git` suffix are normalized and deduplicated before network access. Repository metadata requests use fixed public provider APIs, bounded responses, and timeouts configured by `ARTIFACT_REQUEST_TIMEOUT_SECONDS` (default `10`). Inaccessible repositories remain visible as `INACCESSIBLE`; they do not fail other discoveries.

Artifact relationship and availability are separate graded fields using `FOUND`, `VERIFIED`, `PARTIAL`, `MISSING`, `INACCESSIBLE`, and `AMBIGUOUS`. An HTTP 200 alone never produces `VERIFIED`. Strong deterministic signals such as an explicit paper link plus matching paper title/author or official-implementation wording are required.

Artifacts can be associated with an experiment when the nearby paper context matches its structured model, dataset, metric, or objective. Missing exact dataset/model URLs and versions remain explicit rather than being guessed.

REPROVE does **not** clone repositories, download datasets or model weights, install dependencies, execute scripts/notebooks/containers, or claim that a discovered artifact reproduces the paper.

## Artifact Inspection

Step 3B implements bounded repository metadata, README, and file tree inspection for discovered computational artifacts (e.g., GitHub or GitLab repositories). It securely inspects repositories via public web APIs to build an experiment-to-file mapping without executing any untrusted code or initiating large bulk downloads.

This step deterministically identifies possibly relevant paths within the repository based on file extensions, filenames, and bounded README contextual cues:
- Bounded file classification identifies execution scripts, Python code, checkpoints, models, containers, and configuration files.
- Artifact roles (e.g., `ENTRYPOINT`, `EVALUATION`, `TRAINING`, `MODEL_DEFINITION`) are assigned and validated against specific experimental objectives.
- Relevance is checked using a specific strict stopword list to prevent false positives when searching generic paths.
- Based on available configuration files, dependencies, checkpoints, or code, each experiment mapping calculates a high-level `ArtifactReadiness` metric (such as `COMPLETE`, `PARTIAL`, or `MISSING`).

REPROVE does **not** execute research code. Finding a relevant file does not mean the experiment is reproducible, nor does it guarantee the code functions correctly or yields original reported values.

## Run the web app

In another terminal:

```bash
cd apps/web
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`. `NEXT_PUBLIC_API_URL` defaults to `http://localhost:8000` and can be changed in `apps/web/.env.local`.

## Current analyzer behavior

The Gemini Research Analyzer extracts paper metadata, author-reported scientific claims, experiments, methods, and evidence locations from bounded section-aware context. Gemini is constrained to structured JSON, and every response is parsed and validated against the existing Pydantic `ResearchAnalysis` schema. References are extracted deterministically from the full bibliography through the preserved engine boundary, then pass through scientometric validation. Claim evidence is assessed against available cited text, and Step 3A discovers explicit computational artifacts without executing them before all outputs reach the frontend.

The analyzer reports what the paper says; it does not verify, reproduce, or establish the truth of a scientific claim. Missing values remain `null` or empty arrays rather than being invented.

## Verification

```bash
# Frontend
cd apps/web
npm run lint
npm run build

# Backend startup (from apps/api with the virtual environment active)
pip install -r requirements-dev.txt
pytest
uvicorn app.main:app
```

Example request:

```bash
curl -F "file=@/path/to/paper.pdf;type=application/pdf" \
  http://localhost:8000/api/v1/analyze-paper
```
### STEP 4: Environment Reconstruction
STEP 4 reconstructs documented and observed environment specifications as part of
`POST /api/v1/analyze-paper`. It uses the bounded repository tree and experiment
mappings from Step 3, then reads a prioritized set of environment manifests through
the same repository provider. Results retain source paths, evidence, certainty,
missing information, and unresolved conflicts.

Repository access remains bounded per repository: 200 visible files, directory depth
2, 1 MB per response, 40,000 retained text characters, 6 metadata requests, and 4
content requests by default. These limits are configurable with the existing
`MAX_REPOSITORY_*` environment variables, including
`MAX_REPOSITORY_CONTENT_REQUESTS`.

The reconstruction path only parses content. It does not clone repositories, install
dependencies, execute repository code, build containers, or download datasets and
checkpoints. Environment-variable assignment values are discarded; only names and
secret classification are returned.
