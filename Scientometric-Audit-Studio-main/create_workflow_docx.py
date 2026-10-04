"""
Generates the comprehensive Word (.docx) technical report for the
Scholarly Reference Validation System, complete with the high-resolution
embedded workflow diagram, tables, and methodology specifications.
"""
import os
import sys
from pathlib import Path

# Add project root and .venv site-packages to path
BASE_DIR = Path(__file__).resolve().parent
site_packages = BASE_DIR / ".venv" / "Lib" / "site-packages"
if site_packages.exists() and str(site_packages) not in sys.path:
    sys.path.insert(0, str(site_packages))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def set_cell_background(cell, hex_color):
    """Sets background color of a table cell."""
    tcPr = cell._element.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Sets internal padding for a cell."""
    tcPr = cell._element.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m_name, m_val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m_name}')
        node.set(qn('w:w'), str(m_val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)

def add_callout(doc, text, title="NOTE"):
    """Adds a callout box with a colored left border."""
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = tbl.cell(0, 0)
    set_cell_background(cell, "F1F5F9")
    set_cell_margins(cell, top=140, bottom=140, left=200, right=200)
    
    # Left border only
    tcPr = cell._element.get_or_add_tcPr()
    tcBorders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'<w:top w:val="none"/>'
        f'<w:left w:val="single" w:sz="36" w:space="0" w:color="4F46E5"/>'
        f'<w:bottom w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'</w:tcBorders>'
    )
    tcPr.append(tcBorders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.15
    run_t = p.add_run(f"[{title}] ")
    run_t.bold = True
    run_t.font.name = "Segoe UI"
    run_t.font.size = Pt(10)
    run_t.font.color.rgb = RGBColor(79, 70, 229)
    
    run_body = p.add_run(text)
    run_body.font.name = "Segoe UI"
    run_body.font.size = Pt(10)
    run_body.font.color.rgb = RGBColor(30, 41, 59)
    doc.add_paragraph()  # spacing

def create_document():
    doc = Document()
    
    # Configure 1-inch margins
    sections = doc.sections
    for s in sections:
        s.top_margin = Inches(1.0)
        s.bottom_margin = Inches(1.0)
        s.left_margin = Inches(1.0)
        s.right_margin = Inches(1.0)
        
        # Add footer with page numbering
        footer = s.footer
        f_p = footer.paragraphs[0]
        f_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        f_run = f_p.add_run("Scientometric Reference Validation System — IIT Delhi Research Automation")
        f_run.font.name = "Segoe UI"
        f_run.font.size = Pt(9)
        f_run.font.color.rgb = RGBColor(148, 163, 184)

    # Style defaults
    normal_style = doc.styles['Normal']
    normal_style.font.name = 'Segoe UI'
    normal_style.font.size = Pt(11)
    normal_style.font.color.rgb = RGBColor(51, 65, 85)

    # ==========================================
    # COVER / HEADER SECTION
    # ==========================================
    p_tag = doc.add_paragraph()
    p_tag.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p_tag.paragraph_format.space_after = Pt(4)
    run_tag = p_tag.add_run("TECHNICAL SPECIFICATION & ARCHITECTURE REPORT")
    run_tag.bold = True
    run_tag.font.name = "Segoe UI"
    run_tag.font.size = Pt(9.5)
    run_tag.font.color.rgb = RGBColor(79, 70, 229)

    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_after = Pt(8)
    run_title = p_title.add_run("Scholarly Reference Validation System")
    run_title.bold = True
    run_title.font.name = "Segoe UI"
    run_title.font.size = Pt(26)
    run_title.font.color.rgb = RGBColor(15, 23, 42)

    p_sub = doc.add_paragraph()
    p_sub.paragraph_format.space_after = Pt(16)
    run_sub = p_sub.add_run("Comprehensive End-to-End System Architecture, Multi-Provider Scientometric Pipeline, Decision Taxonomy, and Workflow Specification")
    run_sub.font.name = "Segoe UI"
    run_sub.font.size = Pt(13)
    run_sub.font.color.rgb = RGBColor(100, 116, 139)

    # Metadata table
    meta_table = doc.add_table(rows=4, cols=2)
    meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_data = [
        ("Institutional Project:", "Research Automation & Scientometrics Studio"),
        ("Environment / Affiliation:", "Indian Institute of Technology (IIT) Delhi"),
        ("Platform Version:", "Version 2.0 (Production Release — FastAPI + React)"),
        ("Documentation Scope:", "Ingestion, Segmentation, Provider Layer, Matching Engine, Triage, and UI"),
    ]
    for row_idx, (k, v) in enumerate(meta_data):
        c1, c2 = meta_table.cell(row_idx, 0), meta_table.cell(row_idx, 1)
        c1.width = Inches(2.2)
        c2.width = Inches(4.3)
        set_cell_background(c1, "F8FAFC")
        set_cell_background(c2, "FFFFFF")
        set_cell_margins(c1, top=60, bottom=60, left=100, right=100)
        set_cell_margins(c2, top=60, bottom=60, left=100, right=100)
        
        p1 = c1.paragraphs[0]
        p1.paragraph_format.space_after = Pt(0)
        r1 = p1.add_run(k)
        r1.bold = True
        r1.font.size = Pt(9.5)
        r1.font.color.rgb = RGBColor(71, 85, 105)
        
        p2 = c2.paragraphs[0]
        p2.paragraph_format.space_after = Pt(0)
        r2 = p2.add_run(v)
        r2.font.size = Pt(9.5)
        r2.font.color.rgb = RGBColor(15, 23, 42)

    doc.add_paragraph().paragraph_format.space_after = Pt(14)

    # ==========================================
    # SECTION 1: EXECUTIVE SUMMARY
    # ==========================================
    h1 = doc.add_heading(level=1)
    h1.paragraph_format.space_before = Pt(18)
    h1.paragraph_format.space_after = Pt(8)
    r_h1 = h1.add_run("1. Executive Summary & Core Objectives")
    r_h1.font.name = "Segoe UI"
    r_h1.font.color.rgb = RGBColor(30, 41, 59)

    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.2
    p.paragraph_format.space_after = Pt(8)
    p.add_run(
        "In modern scientometrics and research evaluation, the integrity of academic bibliographies is essential for citation analysis, "
        "impact factor calculation, and automated knowledge graph construction. However, scholarly reference lists in publications frequently suffer "
        "from pervasive data quality issues: phantom or hallucinated DOIs, mismatched identifiers pointing to completely unrelated works, dead URLs, "
        "publisher paywall bot-blocking that masquerades as broken links, and severe typographical corruptions introduced during optical character "
        "recognition (OCR) or reference list compilation."
    )

    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.2
    p.paragraph_format.space_after = Pt(8)
    p.add_run(
        "The Scholarly Reference Validation System was designed and engineered as a high-throughput, dual-mode validation studio. It supports both "
        "corpus-scale batch ingestion (e.g., thousands of citations extracted from institutional Scopus exports) and on-demand live auditing of individual "
        "manuscripts via Scopus URLs/EIDs or custom spreadsheets (.xlsx / .csv). Unlike conventional link-checking tools that only check if a URL responds "
        "with HTTP 200 OK, this system executes multi-attribute scientometric verification—corroborating title similarity, author overlap, publication year, "
        "and venue consistency against authoritative registries."
    )

    add_callout(
        doc,
        "A DOI resolving with HTTP 200 OK does NOT mean the citation is correct. If an author cites a 2019 healthcare paper but mistakenly copies "
        "a DOI belonging to a 2020 financial economics article, naive link-checkers mark it 'Valid'. Our system detects this discrepancy, categorizes it as "
        "VALID_DOI_WRONG_REFERENCE, and flags it for human review.",
        title="CORE SCIENTOMETRIC PRINCIPLE"
    )

    # ==========================================
    # SECTION 2: END-TO-END WORKFLOW DIAGRAM
    # ==========================================
    h1 = doc.add_heading(level=1)
    h1.paragraph_format.space_before = Pt(20)
    h1.paragraph_format.space_after = Pt(8)
    r_h1 = h1.add_run("2. End-to-End System Workflow Diagram")
    r_h1.font.name = "Segoe UI"
    r_h1.font.color.rgb = RGBColor(30, 41, 59)

    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.2
    p.paragraph_format.space_after = Pt(12)
    p.add_run(
        "The following high-resolution workflow diagram presents the complete technical flow of data through all six architectural tiers: "
        "from dual-channel input ingestion and grammar-based citation segmentation to multi-provider ground truth resolution, multi-attribute "
        "scientometric matching, multi-class decision classification, and interactive visualization."
    )

    # Insert Workflow Image
    img_path = str(BASE_DIR / "workflow_diagram.png")
    if os.path.exists(img_path):
        p_img = doc.add_paragraph()
        p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_img.paragraph_format.space_before = Pt(8)
        p_img.paragraph_format.space_after = Pt(6)
        run_img = p_img.add_run()
        run_img.add_picture(img_path, width=Inches(6.5))

        p_cap = doc.add_paragraph()
        p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_cap.paragraph_format.space_after = Pt(16)
        r_cap = p_cap.add_run("Figure 1: Comprehensive System Architecture and Multi-Stage Processing Workflow.")
        r_cap.font.name = "Segoe UI"
        r_cap.font.size = Pt(9.5)
        r_cap.font.italic = True
        r_cap.font.color.rgb = RGBColor(100, 116, 139)

    # ==========================================
    # SECTION 3: ARCHITECTURAL TIERS & METHODOLOGY
    # ==========================================
    h1 = doc.add_heading(level=1)
    h1.paragraph_format.space_before = Pt(18)
    h1.paragraph_format.space_after = Pt(8)
    r_h1 = h1.add_run("3. Detailed Pipeline Stages & Technical Methodology")
    r_h1.font.name = "Segoe UI"
    r_h1.font.color.rgb = RGBColor(30, 41, 59)

    # Stage 1
    h2 = doc.add_heading(level=2)
    h2.paragraph_format.space_before = Pt(12)
    h2.paragraph_format.space_after = Pt(4)
    r_h2 = h2.add_run("Stage 1: Multi-Modal Input & Ingestion Layer")
    r_h2.font.name = "Segoe UI"
    r_h2.font.color.rgb = RGBColor(79, 70, 229)

    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.2
    p.paragraph_format.space_after = Pt(8)
    p.add_run(
        "The system accommodates two complementary ingestion workflows:\n"
        "1. Bulk Corpus Ingestion: Ingests institutional Scopus CSV export dumps containing hundreds of citing manuscripts (864 documents) "
        "and over 17,252 bibliographic citations. Metadata fields include EID, authors, paper title, year, publication venue, and raw reference strings.\n"
        "2. On-Demand Live Audit Studio: Allows researchers to provide an individual Scopus publication link (e.g., https://www.scopus.com/pages/publications/85116424104), "
        "an 11-digit Scopus EID, or upload an ad-hoc spreadsheet (.xlsx / .csv). The system retrieves the publication's live metadata, extracts citations on-the-fly, "
        "and completes full verification within seconds."
    )

    # Stage 2
    h2 = doc.add_heading(level=2)
    h2.paragraph_format.space_before = Pt(12)
    h2.paragraph_format.space_after = Pt(4)
    r_h2 = h2.add_run("Stage 2: Heuristic Reference Segmentation & Delimiter Disambiguation")
    r_h2.font.name = "Segoe UI"
    r_h2.font.color.rgb = RGBColor(79, 70, 229)

    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.2
    p.paragraph_format.space_after = Pt(8)
    p.add_run(
        "A major challenge in scholarly reference extraction is punctuation ambiguity. In standard academic bibliographies, semicolons (;) are used "
        "both to delimit multiple co-authors within a single citation (e.g., 'Aithal PS; Aithal S.') and to separate adjacent references. A naive string "
        "split produces thousands of fragmented author fragments. Our Reference Segmentation Engine (reference_splitter.py) implements heuristic grammar rules "
        "that examine publication patterns (e.g., 4-digit years in parentheses, journal volume/page markers) to identify authentic reference boundaries without splitting authors."
    )

    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.2
    p.paragraph_format.space_after = Pt(8)
    p.add_run(
        "Crucially, the system enforces an immutable audit trail: every citation preserves its raw_reference string alongside its generated reference_id and "
        "citing manuscript EID. The Bibliographic Field Parser (citation_parser.py) then tokenizes cited authors, document title, publication venue, "
        "publication year, volume, and pagination. Concurrently, the DOI Extractor (doi_extractor.py) extracts, cleans, unescapes, and normalizes DOIs into "
        "canonical lowercase format (e.g., 10.xxxx/...). "
    )

    # Stage 3
    h2 = doc.add_heading(level=2)
    h2.paragraph_format.space_before = Pt(12)
    h2.paragraph_format.space_after = Pt(4)
    r_h2 = h2.add_run("Stage 3: Multi-Provider Ground Truth & API Resolution")
    r_h2.font.name = "Segoe UI"
    r_h2.font.color.rgb = RGBColor(79, 70, 229)

    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.2
    p.paragraph_format.space_after = Pt(8)
    p.add_run(
        "To validate citations against primary sources, the system integrates four independent external providers:\n"
        "• Elsevier Scopus Abstract Retrieval API: Retrieves authoritative publication records. To bypass Elsevier's strict 40-item pagination limit "
        "on standard reference views (which previously caused 99-reference papers to show only 40), the client queries view=FULL to parse the entire bibliography "
        "from the authoritative item.bibrecord structure in a single payload.\n"
        "• Crossref REST API: Queries the official registration agency for DOI metadata, verifying publisher registration records, work titles, and landing URLs.\n"
        "• OpenAlex Scholarly Graph: Provides secondary verification for open-access status, retraction warnings, and disambiguated institutional work entities.\n"
        "• Direct DOI Resolver Proxy: Performs HTTP HEAD/GET probes against https://doi.org to evaluate real-time redirect chains and landing page accessibility."
    )

    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.2
    p.paragraph_format.space_after = Pt(8)
    p.add_run(
        "All network interactions are governed by a token-bucket rate limiter (10 req/s for Crossref, 5 req/s for Scopus) and backed by a two-tier persistent "
        "SQLite and disk cache manager (cache_manager.py). Cached queries execute in under 1 millisecond, preventing API exhaustion."
    )

    # Stage 4
    h2 = doc.add_heading(level=2)
    h2.paragraph_format.space_before = Pt(12)
    h2.paragraph_format.space_after = Pt(4)
    r_h2 = h2.add_run("Stage 4: Scientometric Similarity & Diagnostic Matching Engine")
    r_h2.font.name = "Segoe UI"
    r_h2.font.color.rgb = RGBColor(79, 70, 229)

    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.2
    p.paragraph_format.space_after = Pt(8)
    p.add_run(
        "Rather than relying on binary equality, the matching engine computes multi-dimensional similarity metrics:\n"
        "• Title Similarity: Combines token sort ratio and normalized Levenshtein distance. Crucially, Elsevier API bibrecords omit ref-title for non-journal "
        "publications (e.g. McKinsey reports, Accenture whitepapers, Bank of Italy monographs), returning an empty dictionary {}. Our engine falls back to "
        "ref-sourcetitle, restoring accurate title similarity (from 0% to 100%).\n"
        "• Author Similarity: Tokenizes surnames, normalizes initials, and computes Jaro-Winkler string similarity across co-author sets.\n"
        "• Temporal & Venue Consistency: Checks whether publication years match (|ΔYear| ≤ 1) and matches journal abbreviations against full source titles.\n"
        "• Automated DOI Recovery: For references cited without a DOI, the engine performs a targeted title search on Crossref, successfully recovering "
        "missing registered DOIs with high confidence."
    )

    p_f = doc.add_paragraph()
    p_f.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_f.paragraph_format.space_before = Pt(6)
    p_f.paragraph_format.space_after = Pt(10)
    r_f = p_f.add_run("Composite Score = 0.50 × Title_Sim + 0.30 × Author_Sim + 0.10 × Year_Match + 0.10 × Venue_Sim")
    r_f.bold = True
    r_f.font.name = "Consolas"
    r_f.font.size = Pt(11)
    r_f.font.color.rgb = RGBColor(79, 70, 229)

    # Stage 5
    h2 = doc.add_heading(level=2)
    h2.paragraph_format.space_before = Pt(12)
    h2.paragraph_format.space_after = Pt(4)
    r_h2 = h2.add_run("Stage 5: Multi-Class Decision Matrix & Classification Taxonomy")
    r_h2.font.name = "Segoe UI"
    r_h2.font.color.rgb = RGBColor(79, 70, 229)

    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.2
    p.paragraph_format.space_after = Pt(10)
    p.add_run(
        "Every reference is evaluated against a deterministic decision matrix that assigns one of seven primary classifications, "
        "determining whether the citation is auto-approved or routed to the human review triage queue:"
    )

    # Classification Table
    class_table = doc.add_table(rows=8, cols=4)
    class_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["Final Status Classification", "Bibliographic Criteria", "System Action", "Quality Assurance Category"]
    for i, h_text in enumerate(headers):
        cell = class_table.cell(0, i)
        set_cell_background(cell, "1E293B")
        set_cell_margins(cell, top=100, bottom=100, left=120, right=120)
        p_h = cell.paragraphs[0]
        p_h.paragraph_format.space_after = Pt(0)
        r_h = p_h.add_run(h_text)
        r_h.bold = True
        r_h.font.size = Pt(9.5)
        r_h.font.color.rgb = RGBColor(255, 255, 255)

    rows_data = [
        ("VALID_CORRECT", "DOI resolves (200 OK), Title Sim ≥ 70%, and Composite Score ≥ 65%.", "Auto-Approved", "Fully Verified Citation"),
        ("VALID_DOI_WRONG_REFERENCE", "DOI resolves (200 OK), but Title Sim < 35% (points to an unrelated publication).", "Flagged Review", "Hallucinated / Swapped DOI"),
        ("SCOPUS_LINKED_NO_DOI", "Reference matched in Scopus ground truth, but published without an assigned DOI.", "Auto-Approved", "Verified Book / Report"),
        ("DOI_RECOVERED", "No DOI in cited text, but correct DOI identified via Crossref high-confidence title match.", "Auto-Approved", "Recovered Missing Identifier"),
        ("ACCESS_RESTRICTED", "DOI resolves to official publisher domain, but HTTP status is 401/403 (paywall/bot guard).", "Verified Link", "Access-Protected Publication"),
        ("DEAD_LINK / INVALID_DOI", "DOI syntax is invalid, DOI does not exist in registry, or landing server returns HTTP 404.", "Flagged Review", "Broken URL / Defunct Link"),
        ("AMBIGUOUS / UNVERIFIED", "Multiple competing search candidates or similarity scores fall within borderline thresholds.", "Human Triage", "Human Review Queue"),
    ]

    col_widths = [Inches(1.8), Inches(2.5), Inches(1.1), Inches(1.3)]
    for row_idx, r_data in enumerate(rows_data, start=1):
        for col_idx, text_val in enumerate(r_data):
            cell = class_table.cell(row_idx, col_idx)
            cell.width = col_widths[col_idx]
            bg = "F8FAFC" if row_idx % 2 == 1 else "FFFFFF"
            set_cell_background(cell, bg)
            set_cell_margins(cell, top=80, bottom=80, left=100, right=100)
            p_c = cell.paragraphs[0]
            p_c.paragraph_format.space_after = Pt(0)
            r_c = p_c.add_run(text_val)
            r_c.font.size = Pt(9)
            if col_idx == 0:
                r_c.bold = True
                r_c.font.name = "Consolas"
                r_c.font.size = Pt(8.5)
                if "VALID_CORRECT" in text_val or "SCOPUS_LINKED" in text_val or "RECOVERED" in text_val:
                    r_c.font.color.rgb = RGBColor(5, 150, 105)
                elif "WRONG" in text_val or "DEAD" in text_val:
                    r_c.font.color.rgb = RGBColor(220, 38, 38)
                else:
                    r_c.font.color.rgb = RGBColor(217, 119, 6)

    doc.add_paragraph().paragraph_format.space_after = Pt(14)

    # Stage 6
    h2 = doc.add_heading(level=2)
    h2.paragraph_format.space_before = Pt(12)
    h2.paragraph_format.space_after = Pt(4)
    r_h2 = h2.add_run("Stage 6: Storage, Web Studio & Reporting Infrastructure")
    r_h2.font.name = "Segoe UI"
    r_h2.font.color.rgb = RGBColor(79, 70, 229)

    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.2
    p.paragraph_format.space_after = Pt(8)
    p.add_run(
        "The presentation and storage layer is powered by a high-performance stack:\n"
        "• SQLite Database Engine: Maintains references_indexed and documents_summary with full-text search (FTS5) indexes, enabling sub-10ms queries "
        "across 17,252+ citations.\n"
        "• FastAPI REST Server: Provides high-speed asynchronous REST endpoints (/api/references, /api/documents, /api/stats, /api/custom-audit/run, /api/custom-audit/export-excel).\n"
        "• React Reference Studio: A responsive dashboard featuring an 11-column data table, live manuscript filters, status badges, and a dedicated Title Sim column.\n"
        "• Slide-Over Diagnostic Inspector: A drawer providing zero-latency inspection of cited text, resolved metadata, title/author similarity gauges, and automated decision rationales.\n"
        "• Multi-Sheet Excel Exporter: Generates styled workbooks (.xlsx) with dedicated tabs for Executive Summary, Verified Citations, Human Review Queue, and Dead Links."
    )

    # ==========================================
    # SECTION 4: EMPIRICAL CASE STUDIES & VALIDATION
    # ==========================================
    h1 = doc.add_heading(level=1)
    h1.paragraph_format.space_before = Pt(18)
    h1.paragraph_format.space_after = Pt(8)
    r_h1 = h1.add_run("4. Empirical Case Studies & Validation Results")
    r_h1.font.name = "Segoe UI"
    r_h1.font.color.rgb = RGBColor(30, 41, 59)

    case_studies = [
        ("Case Study 1: Resolving the 40-Reference Pagination Ceiling (Paper 85116424104)",
         "Paper 'Artificial intelligence-assisted tools for redefining the communication landscape of the scholarly world' contains 99 references. "
         "Standard Elsevier API endpoints cap responses at 40 items per page. By transitioning to view=FULL bibrecord extraction, the pipeline "
         "successfully extracted, parsed, and audited all 99 of 99 references with 100% Scopus linkage."),
        ("Case Study 2: Restoring Title Similarity for Non-Journal Reports (Paper 105047681813)",
         "Paper 'AI Adoption by Italian Startups: A Measurement Framework' (27 references) cites numerous industry reports (McKinsey, Bank of Italy, Accenture). "
         "These records returned empty dictionaries {} in Elsevier's ref-title field, resulting in 0% title similarity. Implementing ref-sourcetitle "
         "fallbacks restored accurate title similarity scores (100% and 90%) across all report citations."),
        ("Case Study 3: High-Confidence DOI Recovery for Unlinked Citations",
         "Citation #5 in Paper 105047681813 ('An AI adoption model for SMEs...') was cited without a registered DOI. The recovery engine performed a "
         "targeted Crossref title query, successfully identifying and linking DOI 10.1016/j.ifacol.2021.08.082 with a 100% title match and 0.70 composite confidence.")
    ]

    for title_cs, desc_cs in case_studies:
        h3 = doc.add_heading(level=3)
        h3.paragraph_format.space_before = Pt(10)
        h3.paragraph_format.space_after = Pt(3)
        r_h3 = h3.add_run(title_cs)
        r_h3.font.name = "Segoe UI"
        r_h3.font.size = Pt(11)
        r_h3.font.color.rgb = RGBColor(15, 23, 42)

        p_cs = doc.add_paragraph()
        p_cs.paragraph_format.line_spacing = 1.15
        p_cs.paragraph_format.space_after = Pt(6)
        p_cs.add_run(desc_cs)

    # Save document
    output_docx = BASE_DIR / "Scholarly_Reference_Validation_System_Workflow.docx"
    doc.save(str(output_docx))
    print(f"[SUCCESS] Generated complete Word document: {output_docx}")
    print(f"File size: {os.path.getsize(output_docx)} bytes")

if __name__ == "__main__":
    create_document()

