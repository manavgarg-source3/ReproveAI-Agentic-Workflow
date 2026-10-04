"""
Human review queue exporter and audit generator.
Identifies uncertain, ambiguous, mismatch, and wrong-reference records for researcher inspection.
"""
import csv
import logging
from pathlib import Path
from typing import List, Dict, Any
from src.models.verification import VerificationResult, FinalStatus

logger = logging.getLogger(__name__)


class ReviewExporter:
    """
    Exports items requiring manual human review.
    """

    REVIEW_STATUSES = {
        FinalStatus.VALID_DOI_WRONG_REFERENCE,
        FinalStatus.METADATA_MISMATCH,
        FinalStatus.AMBIGUOUS,
        FinalStatus.DOI_RECOVERY_UNCERTAIN,
        FinalStatus.RETRACTED_REFERENCE,
        FinalStatus.INVALID_DOI,
        FinalStatus.BROKEN_URL,
    }

    @classmethod
    def filter_for_review(cls, results: List[VerificationResult]) -> List[VerificationResult]:
        """Filters results that strictly require human review."""
        review_items = []
        for r in results:
            if r.needs_human_review or r.final_status in cls.REVIEW_STATUSES:
                review_items.append(r)
        return review_items

    @classmethod
    def export_csv(cls, results: List[VerificationResult], output_path: Path) -> int:
        """
        Saves human review queue to CSV.
        """
        items = cls.filter_for_review(results)
        if not items:
            logger.info("No items requiring human review.")
            return 0

        output_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(items[0].to_dict().keys())
        
        with open(output_path, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for item in items:
                writer.writerow(item.to_dict())

        logger.info(f"Exported {len(items)} human review cases to {output_path}")
        return len(items)

