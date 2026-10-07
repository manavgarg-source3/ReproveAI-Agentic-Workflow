"""
Compound bibliographic metadata matcher.
Combines title, author, journal, year, volume, and pages into a calibrated score.
"""
from typing import Dict, Any, Optional
import re
from rapidfuzz import fuzz

from config import (
    WEIGHT_TITLE,
    WEIGHT_AUTHOR,
    WEIGHT_JOURNAL,
    WEIGHT_YEAR,
    WEIGHT_VOLUME_PAGE,
)
from src.matching.title_matcher import TitleMatcher
from src.matching.author_matcher import AuthorMatcher


class MetadataMatcher:
    """
    Evaluates total bibliographic agreement between a cited reference and resolved metadata.
    """

    @classmethod
    def evaluate(
        cls,
        cited: Dict[str, Any],
        resolved: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compares cited dict with resolved dict and returns individual metrics and composite score.
        """
        # 1. Title Similarity
        c_title = str(cited.get("cited_title") or "")
        r_title = str(resolved.get("title") or "")
        title_sim = TitleMatcher.similarity(c_title, r_title)

        # 2. Author Similarity
        c_authors = str(cited.get("cited_authors") or "")
        r_authors = str(resolved.get("authors") or "")
        author_sim = AuthorMatcher.similarity(c_authors, r_authors)

        # 3. Journal Similarity
        c_journal = str(cited.get("cited_journal") or "").strip().lower()
        r_journal = str(resolved.get("journal") or "").strip().lower()
        journal_sim = 0.0
        if c_journal and r_journal:
            # Token set ratio handles abbreviations like 'Curr. Sci' vs 'Current Science'
            journal_sim = round(fuzz.token_set_ratio(c_journal, r_journal) / 100.0, 4)

        # 4. Year Match
        c_year = cited.get("cited_year")
        r_year = resolved.get("year")
        year_score = 0.0
        year_match = False

        if c_year and r_year:
            try:
                y1 = int(c_year)
                y2 = int(r_year)
                diff = abs(y1 - y2)
                if diff == 0:
                    year_score = 1.0
                    year_match = True
                elif diff == 1:
                    # Online first vs print publication date tolerance
                    year_score = 0.70
                    year_match = True
                else:
                    year_score = 0.0
                    year_match = False
            except (ValueError, TypeError):
                pass
        elif not c_year and not r_year:
            year_score = 0.5

        # 5. Volume & Pages Match
        c_vol = str(cited.get("cited_volume") or "").strip()
        r_vol = str(resolved.get("volume") or "").strip()
        c_pages = str(cited.get("cited_pages") or "").strip()
        r_pages = str(resolved.get("pages") or "").strip()

        vol_match = bool(c_vol and r_vol and c_vol == r_vol)
        pages_match = False
        if c_pages and r_pages:
            # PDF extraction commonly preserves an en/em dash while registries
            # return an ASCII hyphen. Normalize separators before comparing the
            # first page so this formatting difference cannot change ranking.
            c_p1 = re.split(r"[-‐-―]", c_pages, maxsplit=1)[0].strip()
            r_p1 = re.split(r"[-‐-―]", r_pages, maxsplit=1)[0].strip()
            if c_p1 and r_p1 and c_p1 == r_p1:
                pages_match = True

        vol_pages_score = 0.0
        if vol_match and pages_match:
            vol_pages_score = 1.0
        elif vol_match or pages_match:
            vol_pages_score = 0.60

        # Score only fields that can actually be compared. Otherwise an exact
        # arXiv-style citation with title, authors, and year can never reach the
        # high-confidence threshold merely because it omits journal/volume/pages.
        weighted_components = [
            (WEIGHT_TITLE, title_sim, bool(c_title and r_title)),
            (WEIGHT_AUTHOR, author_sim, bool(c_authors and r_authors)),
            (WEIGHT_JOURNAL, journal_sim, bool(c_journal and r_journal)),
            (WEIGHT_YEAR, year_score, bool(c_year and r_year)),
            (WEIGHT_VOLUME_PAGE, vol_pages_score, bool((c_vol or c_pages) and (r_vol or r_pages))),
        ]
        available_weight = sum(weight for weight, _score, available in weighted_components if available)
        weighted_score = sum(
            weight * score
            for weight, score, available in weighted_components
            if available
        )
        composite_score = weighted_score / available_weight if available_weight else 0.0

        return {
            "title_similarity": round(title_sim, 4),
            "author_similarity": round(author_sim, 4),
            "journal_similarity": round(journal_sim, 4),
            "year_match": year_match,
            "year_score": round(year_score, 4),
            "volume_match": vol_match,
            "pages_match": pages_match,
            "vol_pages_score": round(vol_pages_score, 4),
            "composite_score": round(min(1.0, max(0.0, composite_score)), 4),
        }

