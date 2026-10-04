"""
Backfill script:
1. Backfills source paper metadata (title, authors, year, doi) into checkpoints.sqlite
2. Re-exports CSV, Excel, and HTML dashboard with updated fields.
"""
import sys
from pathlib import Path

# Ensure root is in python path
root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

import config
import sqlite3
import json
import logging
from typing import List

from src.io.csv_loader import load_scopus_csv
from src.models.verification import VerificationResult, FinalStatus, ConfidenceLevel
from src.io.writers import write_results_csv, write_summary_csv, write_excel_report
from src.io.html_report import generate_html_dashboard
from src.review.review_export import ReviewExporter
from config import DEFAULT_INPUT_CSV, OUTPUT_DIR, BASE_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def main():
    print("Loading source documents...")
    docs = load_scopus_csv(DEFAULT_INPUT_CSV)
    doc_map = {d.eid: d for d in docs}
    print(f"Loaded {len(docs)} documents ({len(doc_map)} unique EIDs).")

    db_path = BASE_DIR / "cache" / "checkpoints.sqlite"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT reference_id, source_eid, result_json FROM completed_references")
    rows = cur.fetchall()
    print(f"Scanning {len(rows)} records in {db_path.name}...")

    updated_count = 0
    results: List[VerificationResult] = []

    for ref_id, source_eid, r_json in rows:
        data = json.loads(r_json)
        doc = doc_map.get(source_eid)

        needs_update = False
        if not data.get("source_title") and doc:
            data["source_title"] = doc.title
            data["source_authors"] = doc.authors
            data["source_year"] = doc.year
            data["source_doi"] = doc.doi
            needs_update = True

        if needs_update:
            cur.execute(
                "UPDATE completed_references SET result_json = ? WHERE reference_id = ?",
                (json.dumps(data), ref_id)
            )
            updated_count += 1

        res = VerificationResult(
            reference_id=data.get("reference_id", ref_id),
            source_eid=source_eid,
            source_title=data.get("source_title", ""),
            source_authors=data.get("source_authors", ""),
            source_year=data.get("source_year"),
            source_doi=data.get("source_doi", ""),
            reference_no=int(data.get("reference_no", 0)),
            raw_reference=data.get("raw_reference", ""),
            extracted_doi=data.get("extracted_doi", ""),
            normalized_doi=data.get("normalized_doi", ""),
            doi_exists=bool(data.get("doi_exists", False)),
            doi_resolves=bool(data.get("doi_resolves", False)),
            http_status=data.get("http_status"),
            final_url=data.get("final_url", ""),
            redirect_count=int(data.get("redirect_count", 0)),
            response_time_ms=data.get("response_time_ms"),
            metadata_source=data.get("metadata_source", ""),
            resolved_title=data.get("resolved_title", ""),
            resolved_authors=data.get("resolved_authors", ""),
            resolved_journal=data.get("resolved_journal", ""),
            resolved_year=data.get("resolved_year"),
            resolved_volume=str(data.get("resolved_volume", "")),
            resolved_issue=str(data.get("resolved_issue", "")),
            resolved_pages=str(data.get("resolved_pages", "")),
            is_retracted=bool(data.get("is_retracted", False)),
            title_similarity=float(data.get("title_similarity", 0.0)),
            author_similarity=float(data.get("author_similarity", 0.0)),
            journal_similarity=float(data.get("journal_similarity", 0.0)),
            year_match=bool(data.get("year_match", False)),
            volume_match=bool(data.get("volume_match", False)),
            pages_match=bool(data.get("pages_match", False)),
            composite_score=float(data.get("composite_score", 0.0)),
            confidence=ConfidenceLevel(data.get("confidence", "UNCERTAIN")),
            final_status=FinalStatus(data.get("final_status", "UNVERIFIED")),
            decision_rationale=data.get("decision_rationale", ""),
            needs_human_review=bool(data.get("needs_human_review", False)),
            checked_at=data.get("checked_at", ""),
        )
        results.append(res)

    if updated_count > 0:
        conn.commit()
    conn.close()
    print(f"Backfill complete! Updated {updated_count} records. Total records in memory: {len(results)}.")

    # Sort results deterministically
    results.sort(key=lambda r: r.reference_id)

    # Compute stats
    status_counts = {s.value: sum(1 for r in results if r.final_status == s) for s in FinalStatus}
    stats = {
        "Distinct Documents with References": len(set(r.source_eid for r in results)),
        "Total Documents in Dataset": len(docs),
        "Total References Processed": len(results),
        "References with Resolving DOI": sum(1 for r in results if r.doi_resolves),
        "Missing DOI - Recovered (DOI_RECOVERED)": status_counts.get("DOI_RECOVERED", 0),
        "Missing DOI - Uncertain (DOI_RECOVERY_UNCERTAIN)": status_counts.get("DOI_RECOVERY_UNCERTAIN", 0),
        "Missing DOI - Unrecovered (DOI_MISSING)": status_counts.get("DOI_MISSING", 0),
        "Valid Correct (VALID_CORRECT)": status_counts.get("VALID_CORRECT", 0),
        "Valid DOI Wrong Reference (VALID_DOI_WRONG_REFERENCE)": status_counts.get("VALID_DOI_WRONG_REFERENCE", 0),
        "Access Restricted (ACCESS_RESTRICTED)": status_counts.get("ACCESS_RESTRICTED", 0),
        "Cases Requiring Human Review": sum(1 for r in results if r.needs_human_review),
    }

    # Write files
    print("Writing CSV files...")
    write_results_csv(results, OUTPUT_DIR / "references_validated.csv")
    ReviewExporter.export_csv(results, OUTPUT_DIR / "human_review_queue.csv")
    write_summary_csv(stats, OUTPUT_DIR / "summary_statistics.csv")

    print("Writing multi-sheet Excel workbook...")
    excel_path = OUTPUT_DIR / "reference_validation_results.xlsx"
    write_excel_report(docs, results, stats, excel_path)
    try:
        import shutil
        shutil.copy2(excel_path, BASE_DIR / "reference_validation_results.xlsx")
    except Exception as e:
        logger.warning(f"Could not copy Excel to root: {e}")

    print("Generating HTML dashboards...")
    generate_html_dashboard(results, stats, OUTPUT_DIR / "reference_validation_report.html")
    generate_html_dashboard(results, stats, BASE_DIR / "reference_validation_report.html")

    print("\nVerification Sample of Enriched Columns (First 3 rows):")
    for r in results[:3]:
        print("-" * 80)
        print(f"Reference ID   : {r.reference_id}")
        print(f"Source Paper   : [{r.source_year}] {r.source_title}")
        print(f"Source Authors : {r.source_authors}")
        print(f"Source DOI     : {r.source_doi}")
        print(f"Citation Text  : {r.raw_reference[:90]}...")
        print(f"Extracted DOI  : {r.extracted_doi or 'None'}")
        print(f"Final Status   : {r.final_status.value}")

    print("\nALL FILES EXPORTED SUCCESSFULLY WITH SOURCE PAPER METADATA INCLUDED!")

if __name__ == "__main__":
    main()

