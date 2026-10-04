"""
Phase 1 — Reference Segmentation and Diagnostic Validation.
Loads Scopus CSV, executes heuristic segmentation, produces reference-level datasets,
and reports comprehensive summary statistics.
"""
import csv
import logging
from pathlib import Path
from typing import List, Dict, Any

from config import DEFAULT_INPUT_CSV, INTERMEDIATE_DIR, OUTPUT_DIR, BASE_DIR
from src.io.csv_loader import load_scopus_csv
from src.parsing.reference_splitter import ReferenceSplitter
from src.parsing.citation_parser import CitationParser
from src.models.reference import ParsedReference

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def run_phase1(
    input_csv_path: Path = DEFAULT_INPUT_CSV,
    output_dir: Path = INTERMEDIATE_DIR,
) -> Dict[str, Any]:
    """
    Executes Phase 1 segmentation pipeline.
    """
    logger.info(f"Starting Phase 1 reference segmentation from {input_csv_path}")
    
    # 1. Load documents
    documents = load_scopus_csv(input_csv_path)
    total_docs = len(documents)
    
    # 2. Segment references
    all_references: List[ParsedReference] = []
    doc_ref_counts: List[int] = []
    
    for doc in documents:
        if not doc.references_raw:
            doc_ref_counts.append(0)
            continue
            
        refs = ReferenceSplitter.split(
            references_text=doc.references_raw,
            source_eid=doc.eid,
            source_title=doc.title,
            source_year=doc.year,
            source_doi=doc.doi,
        )
        
        # Enrich each reference with parsed fields
        for r in refs:
            parsed_fields = CitationParser.parse(r.raw_reference)
            r.cited_authors = parsed_fields.get("cited_authors", "")
            r.cited_title = parsed_fields.get("cited_title", "")
            r.cited_journal = parsed_fields.get("cited_journal", "")
            if not r.cited_volume:
                r.cited_volume = parsed_fields.get("cited_volume", "")
            if not r.cited_issue:
                r.cited_issue = parsed_fields.get("cited_issue", "")
            if not r.cited_pages:
                r.cited_pages = parsed_fields.get("cited_pages", "")

        doc.parsed_reference_count = len(refs)
        doc_ref_counts.append(len(refs))
        all_references.extend(refs)

    # 3. Calculate statistics
    total_parsed_refs = len(all_references)
    docs_with_refs = [c for c in doc_ref_counts if c > 0]
    avg_refs = sum(doc_ref_counts) / total_docs if total_docs else 0.0
    avg_refs_non_empty = sum(docs_with_refs) / len(docs_with_refs) if docs_with_refs else 0.0
    min_refs = min(docs_with_refs) if docs_with_refs else 0
    max_refs = max(doc_ref_counts) if doc_ref_counts else 0
    
    no_year_count = sum(1 for r in all_references if not r.has_year)
    multi_year_count = sum(1 for r in all_references if r.year_marker_count > 1)
    needs_review_count = sum(1 for r in all_references if r.needs_review)
    doi_count = sum(1 for r in all_references if r.has_doi)
    url_count = sum(1 for r in all_references if r.has_url)

    stats = {
        "total_documents": total_docs,
        "documents_with_references": len(docs_with_refs),
        "total_parsed_references": total_parsed_refs,
        "avg_references_per_document": round(avg_refs, 2),
        "avg_references_per_non_empty_doc": round(avg_refs_non_empty, 2),
        "min_references": min_refs,
        "max_references": max_refs,
        "no_year_count": no_year_count,
        "multiple_year_count": multi_year_count,
        "needs_review_count": needs_review_count,
        "explicit_doi_count": doi_count,
        "explicit_url_count": url_count,
    }

    # 4. Write primary output: phase1_reference_level_v2.csv in root and intermediate
    output_files = [
        BASE_DIR / "phase1_reference_level_v2.csv",
        output_dir / "phase1_reference_level.csv",
    ]
    
    fieldnames = list(all_references[0].to_dict().keys()) if all_references else []
    for out_path in output_files:
        with open(out_path, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in all_references:
                writer.writerow(r.to_dict())
        logger.info(f"Saved {len(all_references)} records to {out_path}")

    # 5. Write manual review sample
    review_sample_files = [
        BASE_DIR / "phase1_manual_review_sample.csv",
        output_dir / "phase1_manual_review_sample.csv",
    ]
    review_refs = [r for r in all_references if r.needs_review]
    for r_path in review_sample_files:
        with open(r_path, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in review_refs:
                writer.writerow(r.to_dict())
        logger.info(f"Saved {len(review_refs)} suspicious records to {r_path}")

    # 6. Display Summary & 20 Representative references
    print("\n" + "=" * 80)
    print("PHASE 1 SUMMARY STATISTICS")
    print("=" * 80)
    for k, v in stats.items():
        print(f"  {k:35s}: {v}")
    print("=" * 80 + "\n")

    print("=" * 80)
    print("20 REPRESENTATIVE PARSED REFERENCES (INSPECTION SAMPLE)")
    print("=" * 80)
    step = max(1, len(all_references) // 20)
    sample_refs = all_references[::step][:20]
    for idx, r in enumerate(sample_refs, start=1):
        print(f"[{idx:02d}] Source: {r.source_eid} | Ref #{r.reference_no} | Year: {r.cited_year} | DOI: {r.extracted_doi or 'None'}")
        print(f"     Title   : {r.cited_title[:90] if r.cited_title else 'N/A'}")
        print(f"     Authors : {r.cited_authors[:70] if r.cited_authors else 'N/A'}")
        print(f"     Journal : {r.cited_journal[:60] if r.cited_journal else 'N/A'}")
        print(f"     Raw Ref : {r.raw_reference[:100]}...")
        if r.needs_review:
            print(f"     [REVIEW]: {'; '.join(r.review_reasons)}")
        print("-" * 80)

    return stats


if __name__ == "__main__":
    run_phase1()

