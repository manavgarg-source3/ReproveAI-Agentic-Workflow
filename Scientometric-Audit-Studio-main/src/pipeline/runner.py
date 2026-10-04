"""
High-Performance Resumable Pipeline Runner.
Supports multi-threaded concurrency, persistent SQLite checkpointing,
graceful resumption, and multi-sheet reporting.
"""
import time
import json
import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from config import DEFAULT_INPUT_CSV, OUTPUT_DIR, INTERMEDIATE_DIR, BASE_DIR
from src.io.csv_loader import load_scopus_csv
from src.io.writers import write_results_csv, write_summary_csv, write_excel_report
from src.io.html_report import generate_html_dashboard
from src.models.document import SourceDocument
from src.models.reference import ParsedReference
from src.models.verification import VerificationResult, FinalStatus, ConfidenceLevel
from src.parsing.reference_splitter import ReferenceSplitter
from src.parsing.citation_parser import CitationParser
from src.validation.doi_validator import ReferenceValidator
from src.review.review_export import ReviewExporter
from src.matching.title_matcher import TitleMatcher

logger = logging.getLogger(__name__)


class CheckpointManager:
    """
    Persists verified reference records to SQLite so runs can be resumed seamlessly.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (BASE_DIR / "cache" / "checkpoints.sqlite")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS completed_references (
                    reference_id TEXT PRIMARY KEY,
                    source_eid TEXT,
                    result_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

    def get_completed_ids(self) -> Dict[str, VerificationResult]:
        """Returns map of reference_id -> VerificationResult from previous runs."""
        completed = {}
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT reference_id, result_json FROM completed_references")
            for row in cur.fetchall():
                ref_id, r_json = row
                try:
                    data = json.loads(r_json)
                    # Handle final_status safely
                    raw_st = data.get("final_status", "UNVERIFIED")
                    try:
                        status_enum = FinalStatus(raw_st)
                    except ValueError:
                        status_enum = FinalStatus.UNVERIFIED

                    res = VerificationResult(
                        reference_id=data.get("reference_id", ref_id),
                        source_eid=data.get("source_eid", ""),
                        source_title=data.get("source_title", ""),
                        source_authors=data.get("source_authors", ""),
                        source_year=data.get("source_year"),
                        source_doi=data.get("source_doi", ""),
                        reference_no=int(data.get("reference_no", 0)),
                        scopus_linked=bool(data.get("scopus_link_valid", data.get("scopus_linked", False))),
                        scopus_reference_link=data.get("scopus_reference_link", ""),
                        scopus_id=data.get("scopus_id", ""),
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
                        final_status=status_enum,
                        decision_rationale=data.get("decision_rationale", ""),
                        needs_human_review=bool(data.get("needs_human_review", False)),
                        checked_at=data.get("checked_at", ""),
                    )
                    completed[ref_id] = res
                except Exception as e:
                    logger.warning(f"Failed to restore checkpoint for {ref_id}: {e}")
        return completed

    def save_result(self, result: VerificationResult) -> None:
        """Saves or updates a verification result in checkpoints."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO completed_references (reference_id, source_eid, result_json)
                VALUES (?, ?, ?)
                """,
                (result.reference_id, result.source_eid, json.dumps(result.to_dict())),
            )

    def clear(self) -> None:
        """Clears all completed reference checkpoints."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM completed_references")
            conn.commit()
        logger.info("Cleared all checkpoints from completed_references.")


class PipelineRunner:
    """
    Concurrent, resumable orchestrator for reference validation.
    """

    def __init__(
        self,
        input_csv: Path = DEFAULT_INPUT_CSV,
        output_dir: Path = OUTPUT_DIR,
        concurrency: int = 4,
    ):
        self.input_csv = input_csv
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.concurrency = concurrency
        self.validator = ReferenceValidator()
        self.checkpoint = CheckpointManager()

    def run(
        self,
        max_documents: Optional[int] = None,
        max_references: Optional[int] = None,
        resume: bool = True,
    ) -> Dict[str, Any]:
        """
        Executes reference validation with checkpoint resumption and concurrent threads.
        """
        start_time = time.time()
        logger.info(f"Loading input data from {self.input_csv}...")
        documents = load_scopus_csv(self.input_csv)

        if max_documents:
            documents = documents[:max_documents]
            logger.info(f"Limiting execution to first {max_documents} documents.")

        # 1. Segment references
        logger.info("Segmenting references across selected documents...")
        all_refs: List[ParsedReference] = []
        for doc in documents:
            if not doc.references_raw:
                continue
            refs = ReferenceSplitter.split(
                references_text=doc.references_raw,
                source_eid=doc.eid,
                source_title=doc.title,
                source_authors=doc.authors,
                source_year=doc.year,
                source_doi=doc.doi,
            )
            for r in refs:
                parsed = CitationParser.parse(r.raw_reference)
                r.cited_authors = parsed.get("cited_authors", "")
                r.cited_title = parsed.get("cited_title", "")
                r.cited_journal = parsed.get("cited_journal", "")
                if not r.cited_volume:
                    r.cited_volume = parsed.get("cited_volume", "")
                if not r.cited_issue:
                    r.cited_issue = parsed.get("cited_issue", "")
                if not r.cited_pages:
                    r.cited_pages = parsed.get("cited_pages", "")

            doc.parsed_reference_count = len(refs)
            all_refs.extend(refs)

        if max_references and max_references < len(all_refs):
            all_refs = all_refs[:max_references]
            logger.info(f"Limiting verification to first {max_references} references.")

        total_refs = len(all_refs)

        # 2. Checkpoint Resumption
        completed_map = self.checkpoint.get_completed_ids() if resume else {}
        pending_refs = [r for r in all_refs if r.reference_id not in completed_map]
        results: List[VerificationResult] = [completed_map[r.reference_id] for r in all_refs if r.reference_id in completed_map]

        logger.info(
            f"Dataset state: Total target refs: {total_refs} | "
            f"Already completed in checkpoints: {len(results)} | "
            f"Pending validation: {len(pending_refs)}"
        )

        # 3. Concurrent Execution for Pending References (Document-level batching)
        if pending_refs:
            # Group pending references by source document EID
            pending_by_doc: Dict[str, List[ParsedReference]] = {}
            for r in pending_refs:
                pending_by_doc.setdefault(r.source_eid, []).append(r)

            print(f"\nProcessing {len(pending_refs)} pending references across {len(pending_by_doc)} documents using {self.concurrency} concurrent workers...")

            def process_doc_references(eid: str, doc_refs: List[ParsedReference]) -> List[VerificationResult]:
                # 1. Fetch Scopus ground truth references
                scopus_refs = self.validator.scopus.get_abstract_references(eid)
                scopus_map = {sr["reference_no"]: sr for sr in scopus_refs}

                # 2. Track assigned DOIs in this document to prevent duplicate assignments
                assigned_dois = set()
                for r in doc_refs:
                    comp = completed_map.get(r.reference_id)
                    if comp and comp.normalized_doi:
                        assigned_dois.add(comp.normalized_doi.lower())

                # 3. Validate each reference
                doc_results = []
                for ref in doc_refs:
                    s_ref = scopus_map.get(ref.reference_no)
                    if s_ref and ref.cited_title and len(ref.cited_title) > 10 and s_ref.get("title"):
                        t_sim = TitleMatcher.similarity(ref.cited_title, s_ref["title"])
                        if t_sim < 0.35 and len(scopus_refs) > 1:
                            best_cand = None
                            best_cand_sim = 0.35
                            for cand in scopus_refs:
                                if cand.get("title"):
                                    cand_sim = TitleMatcher.similarity(ref.cited_title, cand["title"])
                                    if cand_sim > best_cand_sim:
                                        best_cand_sim = cand_sim
                                        best_cand = cand
                            if best_cand and best_cand_sim >= 0.70:
                                s_ref = best_cand
                    elif not s_ref and ref.cited_title and len(ref.cited_title) > 10:
                        for cand in scopus_refs:
                            if cand.get("title") and TitleMatcher.similarity(ref.cited_title, cand["title"]) >= 0.70:
                                s_ref = cand
                                break

                    try:
                        res = self.validator.validate_reference(ref, scopus_ref=s_ref, assigned_dois=assigned_dois)
                    except Exception as e:
                        logger.error(f"Error validating ref {ref.reference_id}: {e}")
                        res = VerificationResult(
                            reference_id=ref.reference_id,
                            source_eid=ref.source_eid,
                            source_title=ref.source_title,
                            source_authors=ref.source_authors,
                            source_year=ref.source_year,
                            source_doi=ref.source_doi,
                            reference_no=ref.reference_no,
                            raw_reference=ref.raw_reference,
                            scopus_linked=bool(s_ref.get("scopus_linked", False)) if s_ref else False,
                            scopus_reference_link=s_ref.get("scopus_link", "") if s_ref else "Not linked in Scopus",
                            scopus_id=s_ref.get("scopus_id", "") if s_ref else "",
                            decision_rationale=f"Pipeline exception: {e}",
                            final_status=FinalStatus.UNVERIFIED,
                            needs_human_review=True,
                        )
                    doc_results.append(res)
                    self.checkpoint.save_result(res)
                return doc_results

            completed_counter = 0
            with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
                future_to_doc = {
                    executor.submit(process_doc_references, eid, doc_refs): (eid, doc_refs)
                    for eid, doc_refs in pending_by_doc.items()
                }

                with tqdm(total=len(pending_refs), desc="Validating References", unit="ref") as pbar:
                    for future in as_completed(future_to_doc):
                        eid, doc_refs = future_to_doc[future]
                        try:
                            doc_res = future.result()
                            results.extend(doc_res)
                        except Exception as e:
                            logger.error(f"Error processing doc {eid}: {e}")
                        
                        pbar.update(len(doc_refs))
                        completed_counter += len(doc_refs)

                        # Periodic flush every 250 references to keep reports live
                        if completed_counter % 250 < len(doc_refs) or completed_counter % 250 == 0:
                            try:
                                write_results_csv(results, self.output_dir / "references_validated.csv")
                                ReviewExporter.export_csv(results, self.output_dir / "human_review_queue.csv")
                                intermediate_stats = self._compute_statistics(documents, results, round(time.time() - start_time, 2))
                                write_summary_csv(intermediate_stats, self.output_dir / "summary_statistics.csv")
                                excel_path = self.output_dir / "reference_validation_results.xlsx"
                                write_excel_report(documents, results, intermediate_stats, excel_path)
                                try:
                                    import shutil
                                    shutil.copy2(excel_path, BASE_DIR / "reference_validation_results.xlsx")
                                except Exception:
                                    pass
                                generate_html_dashboard(results, intermediate_stats, BASE_DIR / "reference_validation_report.html")
                                generate_html_dashboard(results, intermediate_stats, self.output_dir / "reference_validation_report.html")
                            except Exception as flush_err:
                                logger.warning(f"Periodic flush error (non-fatal): {flush_err}")

        # Sort results deterministically by reference_id
        results.sort(key=lambda r: r.reference_id)
        elapsed_sec = round(time.time() - start_time, 2)

        # 4. Compute Comprehensive KPI Statistics
        stats = self._compute_statistics(documents, results, elapsed_sec)

        # 5. Export all outputs
        logger.info("Exporting CSV and Excel reports...")
        csv_results_path = self.output_dir / "references_validated.csv"
        csv_review_path = self.output_dir / "human_review_queue.csv"
        csv_stats_path = self.output_dir / "summary_statistics.csv"
        excel_path = self.output_dir / "reference_validation_results.xlsx"
        root_excel = BASE_DIR / "reference_validation_results.xlsx"

        write_results_csv(results, csv_results_path)
        ReviewExporter.export_csv(results, csv_review_path)
        write_summary_csv(stats, csv_stats_path)
        write_excel_report(documents, results, stats, excel_path)

        html_path = self.output_dir / "reference_validation_report.html"
        root_html = BASE_DIR / "reference_validation_report.html"
        generate_html_dashboard(results, stats, html_path)
        generate_html_dashboard(results, stats, root_html)
        
        try:
            import shutil
            shutil.copy2(excel_path, root_excel)
            shutil.copy2(csv_results_path, BASE_DIR / "references_validated.csv")
            shutil.copy2(csv_review_path, BASE_DIR / "human_review_queue.csv")
            shutil.copy2(csv_stats_path, BASE_DIR / "summary_statistics.csv")
        except Exception:
            pass

        self._print_summary(stats)
        return stats

    def _compute_statistics(
        self,
        docs: List[SourceDocument],
        results: List[VerificationResult],
        elapsed_sec: float,
    ) -> Dict[str, Any]:
        total_refs = len(results)
        status_counts = {}
        for s in FinalStatus:
            status_counts[s.value] = sum(1 for r in results if r.final_status == s)

        review_count = sum(1 for r in results if r.needs_human_review)
        resolving_doi_count = sum(1 for r in results if r.doi_resolves)

        return {
            "Documents Analyzed": len(docs),
            "References Analyzed": total_refs,
            "Execution Time (seconds)": elapsed_sec,
            "References Linked in Scopus (scopus_link_valid)": sum(1 for r in results if r.scopus_linked),
            "References Unlinked in Scopus": sum(1 for r in results if not r.scopus_linked),
            "References with Resolving DOI": resolving_doi_count,
            "Valid Correct (VALID_CORRECT)": status_counts.get(FinalStatus.VALID_CORRECT.value, 0),
            "Valid Redirect Correct (VALID_REDIRECT_CORRECT)": status_counts.get(FinalStatus.VALID_REDIRECT_CORRECT.value, 0),
            "VALID DOI BUT WRONG REFERENCE (VALID_DOI_WRONG_REFERENCE)": status_counts.get(FinalStatus.VALID_DOI_WRONG_REFERENCE.value, 0),
            "Scopus Linked without DOI (SCOPUS_LINKED_NO_DOI)": status_counts.get(FinalStatus.SCOPUS_LINKED_NO_DOI.value, 0),
            "Scopus Unlinked (SCOPUS_UNLINKED)": status_counts.get(FinalStatus.SCOPUS_UNLINKED.value, 0),
            "Invalid DOI (INVALID_DOI)": status_counts.get(FinalStatus.INVALID_DOI.value, 0),
            "Broken URL (BROKEN_URL)": status_counts.get(FinalStatus.BROKEN_URL.value, 0),
            "Access Restricted / Paywall (ACCESS_RESTRICTED)": status_counts.get(FinalStatus.ACCESS_RESTRICTED.value, 0),
            "Missing DOI - Recovered (DOI_RECOVERED)": status_counts.get(FinalStatus.DOI_RECOVERED.value, 0),
            "Missing DOI - Uncertain (DOI_RECOVERY_UNCERTAIN)": status_counts.get(FinalStatus.DOI_RECOVERY_UNCERTAIN.value, 0),
            "Missing DOI - Unrecovered (DOI_MISSING)": status_counts.get(FinalStatus.DOI_MISSING.value, 0),
            "Metadata Mismatch (METADATA_MISMATCH)": status_counts.get(FinalStatus.METADATA_MISMATCH.value, 0),
            "Retracted Publication (RETRACTED_REFERENCE)": status_counts.get(FinalStatus.RETRACTED_REFERENCE.value, 0),
            "Ambiguous (AMBIGUOUS)": status_counts.get(FinalStatus.AMBIGUOUS.value, 0),
            "Unverified (UNVERIFIED)": status_counts.get(FinalStatus.UNVERIFIED.value, 0),
            "Cases Requiring Human Review": review_count,
        }

    def _print_summary(self, stats: Dict[str, Any]) -> None:
        print("\n" + "=" * 80)
        print("PIPELINE EXECUTION SUMMARY & SCIENTOMETRIC AUDIT")
        print("=" * 80)
        for k, v in stats.items():
            print(f"  {k:55s}: {v}")
        print("=" * 80 + "\n")
