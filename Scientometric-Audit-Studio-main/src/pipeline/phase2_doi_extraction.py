"""
Phase 2 — DOI Extraction and Normalization.
Extracts explicit DOIs from all segmented references, normalizes them canonically,
and generates summary diagnostics on explicit DOI coverage.
"""
import csv
import logging
from pathlib import Path
from typing import Dict, Any, List

from config import INTERMEDIATE_DIR, BASE_DIR
from src.parsing.doi_extractor import extract_doi, normalize_doi, extract_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def run_phase2(
    input_file: Path = INTERMEDIATE_DIR / "phase1_reference_level.csv",
    output_file: Path = INTERMEDIATE_DIR / "phase2_doi_extracted.csv",
) -> Dict[str, Any]:
    """
    Executes Phase 2 DOI extraction and canonical normalization.
    """
    if not input_file.exists():
        input_file = BASE_DIR / "phase1_reference_level_v2.csv"
        
    logger.info(f"Starting Phase 2 DOI extraction from {input_file}")
    
    records: List[Dict[str, Any]] = []
    with open(input_file, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_ref = row.get("raw_reference", "")
            
            # Extract and normalize
            extracted_doi = extract_doi(raw_ref) or ""
            extracted_url = extract_url(raw_ref) or ""
            
            row["extracted_doi"] = extracted_doi
            row["extracted_url"] = extracted_url
            row["has_doi"] = "True" if extracted_doi else "False"
            row["has_url"] = "True" if extracted_url else "False"
            
            records.append(row)

    total_refs = len(records)
    doi_count = sum(1 for r in records if r["extracted_doi"])
    url_count = sum(1 for r in records if r["extracted_url"])
    doi_missing_count = total_refs - doi_count

    stats = {
        "total_references": total_refs,
        "references_with_explicit_doi": doi_count,
        "references_with_url_no_doi": url_count,
        "references_missing_doi": doi_missing_count,
        "explicit_doi_percentage": round((doi_count / total_refs * 100), 2) if total_refs else 0.0,
    }

    # Save output
    fieldnames = list(records[0].keys()) if records else []
    with open(output_file, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow(r)

    logger.info(f"Phase 2 complete: saved {len(records)} records to {output_file}")
    print("\n" + "=" * 80)
    print("PHASE 2 SUMMARY STATISTICS")
    print("=" * 80)
    for k, v in stats.items():
        print(f"  {k:35s}: {v}")
    print("=" * 80 + "\n")

    return stats


if __name__ == "__main__":
    run_phase2()

