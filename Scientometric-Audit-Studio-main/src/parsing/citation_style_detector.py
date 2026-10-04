"""
In-Text Citation Style Classifier and Consistency Engine.
Classifies citation style families (Numeric, Author-Year, Vancouver, Footnote),
extracts in-text citations with sentence contexts, and audits consistency
against the extracted bibliography (detecting orphan and missing references).
"""
import re
import unicodedata
from enum import Enum
from typing import List, Dict, Any, Set, Tuple, Optional


class CitationStyleFamily(str, Enum):
    NUMERIC_BRACKETED = "NUMERIC_BRACKETED"            # [1], [1, 2], [1-5]
    NUMERIC_PARENTHETICAL = "NUMERIC_PARENTHETICAL"    # (1), (1, 2)
    NUMERIC_SUPERSCRIPT = "NUMERIC_SUPERSCRIPT"        # ¹, ², ³
    AUTHOR_YEAR = "AUTHOR_YEAR"                        # (Smith, 2020), Smith (2020)
    FOOTNOTE_NOTE = "FOOTNOTE_NOTE"                    # [Footnote] ...
    UNKNOWN = "UNKNOWN"


STYLE_DISPLAY_NAMES = {
    CitationStyleFamily.NUMERIC_BRACKETED: "IEEE / Numeric Bracketed [1..n]",
    CitationStyleFamily.NUMERIC_PARENTHETICAL: "Numeric Parenthetical (1..n)",
    CitationStyleFamily.NUMERIC_SUPERSCRIPT: "Vancouver / Superscript Numeric",
    CitationStyleFamily.AUTHOR_YEAR: "APA / Harvard Author-Year (Name, Year)",
    CitationStyleFamily.FOOTNOTE_NOTE: "Chicago / Footnote Notes",
    CitationStyleFamily.UNKNOWN: "Mixed / Unidentified Style",
}


def unroll_numeric_range(token: str) -> List[int]:
    """
    Unrolls compound numeric citations like '1-4, 7, 9-11' into [1, 2, 3, 4, 7, 9, 10, 11].
    Handles hyphens, en-dashes, em-dashes, and commas.
    Handles hyphens, en-dashes, em-dashes, commas, and internal digit whitespace (e.g. '1 0' -> 10).
    """
    results = []
    # Split on commas and semicolons
    parts = re.split(r'[,;]', token)
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # Check for range: e.g. 1-4 or 1–4
        m_range = re.match(r'^(\d+)\s*[-–—]\s*(\d+)$', p)
        m_range = re.match(r'^(\d+(?:\s+\d+)*)\s*[-–—]\s*(\d+(?:\s+\d+)*)$', p)
        if m_range:
            start, end = int(m_range.group(1)), int(m_range.group(2))
            start = int(re.sub(r'\s+', '', m_range.group(1)))
            end = int(re.sub(r'\s+', '', m_range.group(2)))
            if start <= end and (end - start) < 50:
                results.extend(list(range(start, end + 1)))
            else:
                results.append(start)
                results.append(end)
        elif p.isdigit():
            results.append(int(p))
        else:
            p_clean = re.sub(r'\s+', '', p)
            if p_clean.isdigit():
                results.append(int(p_clean))
    return sorted(list(set(results)))


def extract_sentence_context(text: str, start_idx: int, end_idx: int, max_window: int = 120) -> str:
    """
    Extracts a neat snippet around the citation marker for UI and verification reporting.
    """
    left = max(0, start_idx - max_window)
    right = min(len(text), end_idx + max_window)

    snippet = text[left:right].strip()
    # Replace linebreaks with spaces
    snippet = re.sub(r'\s+', ' ', snippet)
    return snippet


class CitationStyleDetector:
    """
    Detects the citation style family and extracts in-text citation instances.
    """

    # Bracketed numeric pattern: e.g. [1], [1, 2], [1-5], [1 0], [1, p. 25]
    PAT_NUMERIC_BRACKETED = re.compile(
        r'\[\s*(\d+(?:\s+\d+)*(?:\s*[-–—,;]\s*\d+(?:\s+\d+)*)*)\s*(?:,\s*p{1,2}\.?\s*\d+)?\s*\]'
    )

    # Parenthetical numeric: e.g. (1), (1, 2) (excluding equation references like '(Eq. 1)')
    PAT_NUMERIC_PARENTHETICAL = re.compile(
        r'(?<![A-Za-z0-9_])\(\s*(\d+(?:\s*[-–—,;]\s*\d+)*)\s*\)(?![A-Za-z0-9_])'
    )

    # Unicode superscripts: ¹, ², ³, ⁴, etc.
    SUPERSCRIPT_MAP = {
        '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
        '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9',
        '⁻': '-', '–': '-', '—': '-'
    }
    PAT_SUPERSCRIPT = re.compile(r'([⁰¹²³⁴⁵⁶⁷⁸⁹]+(?:[-–—,][⁰¹²³⁴⁵⁶⁷⁸⁹]+)*)')

    # Author-Year Parenthetical: e.g. (Smith, 2020), (Smith 2020), (Smith & Jones, 2019), (Smith et al. 2021a, 392), (Google n.d.a)
    PAT_AY_PARENTHETICAL = re.compile(
        r'\(([A-Z][A-Za-z\u00C0-\u024F\-\']+(?:\s+(?:&|and)\s+[A-Z][A-Za-z\u00C0-\u024F\-\']+|\s+et\s+al\.)?,?\s*(?:(?:18|19|20)\d{2}[a-z]?|n\.d\.[a-z]?)(?:,\s*(?:p{1,2}\.?\s*)?\d{1,4})?(?:;[^\)]+)?)\)'
    )

    # Author-Year Narrative: e.g. Smith (2020) argued that... or Zhang et al. (2021) or Yang and Perrin (2014)
    PAT_AY_NARRATIVE = re.compile(
        r'\b([A-Z][A-Za-z\u00C0-\u024F\-\']+(?:\s+(?:&|and)\s+[A-Z][A-Za-z\u00C0-\u024F\-\']+|\s+et\s+al\.)?)\s*(?:and\s+[a-z\s]+)?\(\s*((?:18|19|20)\d{2}[a-z]?|n\.d\.[a-z]?)(?:,\s*(?:p{1,2}\.?\s*)?\d{1,4})?\s*\)'
    )

    @classmethod
    def scan_in_text_citations(cls, body_text: str) -> Tuple[CitationStyleFamily, List[Dict[str, Any]]]:
        """
        Scans body_text for in-text citations and determines the dominant style family.
        Returns (dominant_style, list_of_citation_instances).
        """
        if not body_text:
            return CitationStyleFamily.UNKNOWN, []

        bracketed_matches = []
        for m in cls.PAT_NUMERIC_BRACKETED.finditer(body_text):
            raw_marker = m.group(0)
            inner_num = m.group(1)
            unrolled = unroll_numeric_range(inner_num)
            ctx = extract_sentence_context(body_text, m.start(), m.end())
            bracketed_matches.append({
                "type": "NUMERIC_BRACKETED",
                "marker": raw_marker,
                "unrolled_keys": unrolled,
                "context": ctx,
                "start": m.start(),
                "end": m.end()
            })

        ay_matches = []
        # Parenthetical (Smith, 2020) or (Smith 2020, 45)
        for m in cls.PAT_AY_PARENTHETICAL.finditer(body_text):
            raw_marker = m.group(0)
            content = m.group(1)
            ctx = extract_sentence_context(body_text, m.start(), m.end())
            ay_matches.append({
                "type": "AUTHOR_YEAR_PARENTHETICAL",
                "marker": raw_marker,
                "content": content,
                "context": ctx,
                "start": m.start(),
                "end": m.end()
            })

        # Narrative Smith (2020)
        for m in cls.PAT_AY_NARRATIVE.finditer(body_text):
            author = m.group(1).strip()
            year = m.group(2).strip()
            # Filter out non-author tokens like "Table (2020)", "Figure (2020)", "Section (2020)"
            if author.lower() in ("table", "figure", "fig", "section", "equation", "eq", "step", "article", "date"):
                continue
            raw_marker = f"{author} ({year})"
            ctx = extract_sentence_context(body_text, m.start(), m.end())
            ay_matches.append({
                "type": "AUTHOR_YEAR_NARRATIVE",
                "marker": raw_marker,
                "author": author,
                "year": year,
                "context": ctx,
                "start": m.start(),
                "end": m.end()
            })

        superscript_matches = []
        for m in cls.PAT_SUPERSCRIPT.finditer(body_text):
            sup_str = m.group(1)
            # Convert to ascii numbers
            converted = "".join(cls.SUPERSCRIPT_MAP.get(ch, ch) for ch in sup_str)
            unrolled = unroll_numeric_range(converted)
            if unrolled:
                ctx = extract_sentence_context(body_text, m.start(), m.end())
                superscript_matches.append({
                    "type": "NUMERIC_SUPERSCRIPT",
                    "marker": sup_str,
                    "unrolled_keys": unrolled,
                    "context": ctx,
                    "start": m.start(),
                    "end": m.end()
                })

        parenthetical_num_matches = []
        for m in cls.PAT_NUMERIC_PARENTHETICAL.finditer(body_text):
            # Check context to avoid picking up equation numbers, list enumerations like (1), (2), or standalone years like (2016)
            ctx = extract_sentence_context(body_text, m.start(), m.end())
            if re.search(r'\b(eq|equation|formula|step|clause|case|figure|fig|table)\b', ctx, re.IGNORECASE):
                continue
            # Also check if it's an enumerated list item e.g. "(1) Create...", "(2) Place..."
            if re.search(r'\(\s*\d+\s*\)\s+[A-Z][a-z]+', ctx):
                continue
            unrolled = unroll_numeric_range(m.group(1))
            # Ignore parenthetical years (e.g. 1900-2099) unless part of bracketed numeric list
            valid_keys = [k for k in unrolled if k < 1900]
            if not valid_keys:
                continue
            parenthetical_num_matches.append({
                "type": "NUMERIC_PARENTHETICAL",
                "marker": m.group(0),
                "unrolled_keys": valid_keys,
                "context": ctx,
                "start": m.start(),
                "end": m.end()
            })

        footnote_matches = []
        for m in re.finditer(r'\[(?:Footnote|Note)\]\s*(\d{1,4})?\.?\s*(.*?)(?=\n|\[(?:Footnote|Note)\]|$)', body_text, re.IGNORECASE):
            raw_marker = m.group(0)
            note_num = m.group(1)
            ctx = extract_sentence_context(body_text, m.start(), m.end())
            footnote_matches.append({
                "type": "FOOTNOTE_NOTE",
                "marker": f"[{note_num}]" if note_num else "[Footnote]",
                "unrolled_keys": [int(note_num)] if note_num and note_num.isdigit() else [len(footnote_matches) + 1],
                "content": m.group(2).strip(),
                "context": ctx,
                "start": m.start(),
                "end": m.end()
            })

        # Determine dominant style family
        counts = {
            CitationStyleFamily.NUMERIC_BRACKETED: len(bracketed_matches),
            CitationStyleFamily.AUTHOR_YEAR: len(ay_matches),
            CitationStyleFamily.NUMERIC_SUPERSCRIPT: len(superscript_matches),
            CitationStyleFamily.NUMERIC_PARENTHETICAL: len(parenthetical_num_matches),
            CitationStyleFamily.FOOTNOTE_NOTE: len(footnote_matches),
        }

        dominant_style = max(counts, key=counts.get)
        dominant_count = counts[dominant_style]

        if dominant_count == 0:
            return CitationStyleFamily.UNKNOWN, []

        if dominant_style == CitationStyleFamily.NUMERIC_BRACKETED:
            return dominant_style, bracketed_matches
        elif dominant_style == CitationStyleFamily.AUTHOR_YEAR:
            return dominant_style, ay_matches
        elif dominant_style == CitationStyleFamily.NUMERIC_SUPERSCRIPT:
            return dominant_style, superscript_matches
        elif dominant_style == CitationStyleFamily.FOOTNOTE_NOTE:
            return dominant_style, footnote_matches
        else:
            return dominant_style, parenthetical_num_matches


class CitationConsistencyAuditor:
    """
    Cross-references in-text citations against the extracted bibliography.
    Detects orphan references (uncited in text) and missing references (cited in text, missing in bibliography).
    """

    @classmethod
    def audit_consistency(
        cls,
        style: CitationStyleFamily,
        in_text_citations: List[Dict[str, Any]],
        bibliography_items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Computes consistency metrics between in-text citations and the bibliography.
        """
        total_in_text = len(in_text_citations)
        total_bib = len(bibliography_items)

        if style in (CitationStyleFamily.NUMERIC_BRACKETED, CitationStyleFamily.NUMERIC_SUPERSCRIPT, CitationStyleFamily.NUMERIC_PARENTHETICAL, CitationStyleFamily.FOOTNOTE_NOTE):
            # Gather all numeric keys cited in text
            cited_keys = set()
            for c in in_text_citations:
                for k in c.get("unrolled_keys", []):
                    cited_keys.add(k)

            # Bibliography reference numbers (1-indexed)
            bib_keys = set()
            for idx, item in enumerate(bibliography_items, start=1):
                ref_no = item.get("reference_no", idx)
                bib_keys.add(int(ref_no))

            orphan_keys = sorted(list(bib_keys - cited_keys))
            missing_keys = sorted(list(cited_keys - bib_keys))

            # Sequence gaps in text
            max_cited = max(cited_keys) if cited_keys else 0
            sequence_gaps = [n for n in range(1, max_cited + 1) if n not in cited_keys]

            # Calculate consistency score
            penalty = len(orphan_keys) * 1.5 + len(missing_keys) * 3.0
            base_score = 100.0 - (penalty / max(1, total_bib) * 100.0)
            score = max(0.0, min(100.0, round(base_score, 1)))

            return {
                "style_family": style.value,
                "style_display": STYLE_DISPLAY_NAMES.get(style, style.value),
                "total_in_text_instances": total_in_text,
                "distinct_keys_cited": len(cited_keys),
                "total_bibliography_entries": total_bib,
                "orphan_count": len(orphan_keys),
                "orphan_reference_numbers": orphan_keys,
                "missing_count": len(missing_keys),
                "missing_reference_numbers": [f"[{k}]" for k in missing_keys],
                "sequence_gaps": sequence_gaps,
                "consistency_score": score,
                "is_consistent": len(orphan_keys) == 0 and len(missing_keys) == 0
            }

        elif style == CitationStyleFamily.AUTHOR_YEAR:
            # Author-Year matching logic
            cited_authors = set()
            for c in in_text_citations:
                content = c.get("content") or c.get("author") or ""
                # Normalize author surname
                clean_name = re.sub(r'[^A-Za-z]', '', content.split()[0].lower()) if content else ""
                year_m = re.search(r'(?:19|20)\d{2}', c.get("marker", ""))
                year = year_m.group(0) if year_m else ""
                if clean_name and year:
                    cited_authors.add(f"{clean_name}_{year}")

            bib_authors = set()
            for item in bibliography_items:
                authors_str = item.get("cited_authors") or item.get("resolved_authors") or item.get("raw_reference", "")
                primary_author = authors_str.split(';')[0].split(',')[0].strip()
                clean_name = re.sub(r'[^A-Za-z]', '', primary_author.split()[-1].lower()) if primary_author else ""
                year = str(item.get("cited_year") or item.get("resolved_year") or "")
                if clean_name and year:
                    bib_authors.add(f"{clean_name}_{year}")

            orphan_authors = sorted(list(bib_authors - cited_authors))
            missing_authors = sorted(list(cited_authors - bib_authors))

            penalty = len(orphan_authors) * 1.5 + len(missing_authors) * 3.0
            base_score = 100.0 - (penalty / max(1, total_bib) * 100.0)
            score = max(0.0, min(100.0, round(base_score, 1)))

            return {
                "style_family": style.value,
                "style_display": STYLE_DISPLAY_NAMES.get(style, style.value),
                "total_in_text_instances": total_in_text,
                "distinct_keys_cited": len(cited_authors),
                "total_bibliography_entries": total_bib,
                "orphan_count": len(orphan_authors),
                "orphan_reference_numbers": orphan_authors,
                "missing_count": len(missing_authors),
                "missing_reference_numbers": missing_authors,
                "sequence_gaps": [],
                "consistency_score": score,
                "is_consistent": len(orphan_authors) == 0 and len(missing_authors) == 0
            }

        else:
            return {
                "style_family": style.value,
                "style_display": STYLE_DISPLAY_NAMES.get(style, style.value),
                "total_in_text_instances": total_in_text,
                "total_bibliography_entries": total_bib,
                "orphan_count": 0,
                "missing_count": 0,
                "consistency_score": 100.0,
                "is_consistent": True
            }

