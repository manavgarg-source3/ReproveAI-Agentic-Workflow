"""
Robust heuristic reference segmentation engine.
Splits Scopus composite reference strings without naive semicolon splitting,
respecting multi-author semicolon separators and publication-year boundaries.
"""
import re
from typing import List, Optional, Tuple
from src.models.reference import ParsedReference
from src.parsing.doi_extractor import extract_doi, extract_url
from src.parsing.normalizer import normalize_whitespace

# Regex for parenthesized year at the end of a segment
YEAR_MARKER_END_REGEX = re.compile(r"\(\s*(?:18|19|20)\d{2}[a-z]?\s*\)\s*$", re.IGNORECASE)

# Regex for parenthesized year anywhere in the segment
YEAR_MARKER_ANY_REGEX = re.compile(r"\(\s*((?:18|19|20)\d{2}[a-z]?)\s*\)", re.IGNORECASE)

# Regex for 4-digit year anywhere
YEAR_4DIGIT_REGEX = re.compile(r"\b((?:18|19|20)\d{2})\b")

# Regex to detect author-like pattern starting a token (e.g. "Smith J.", "Gupta B.M.,", "Kumar H.A.;")
AUTHOR_START_REGEX = re.compile(
    r"^[A-Z][a-zA-Z\-']{1,25}\s+(?:[A-Z]\.?){1,3}(?:;|,|\.|\s)",
    re.UNICODE,
)


class ReferenceSplitter:
    """
    Stateful and heuristic reference splitter that handles overloaded semicolons.
    """

    @classmethod
    def normalize_bracket_spacing(cls, text: str) -> str:
        """
        Normalizes internal spacing in numbered brackets caused by PDF kerning / sub-pixel glyph layouts:
        e.g. '[ 1 ]' -> '[1]', '[1 0]' -> '[10]', '[15 ]' -> '[15]', '[ 24 ]' -> '[24]'.
        Does NOT alter compound ranges like '[1-3]' or lists like '[1, 2]'.
        """
        if not text:
            return ""
        return re.sub(
            r'\[\s*(\d+)(?:\s+(\d+))*\s*\]',
            lambda m: '[' + re.sub(r'\s+', '', m.group(0)[1:-1]) + ']',
            text
        )

    @classmethod
    def _subsplit_inline_numbered_references(cls, parts: List[str]) -> List[str]:
        """
        Post-processor that splits any part that internally contains merged numbered references
        (e.g., when soft-hyphenation or PDF reflow lost newlines between citations: '...[22] Kumar').
        """
        pattern_bracket = r'(?=(?:^|(?<=[\s\.\>\)\]\"\”\’]))\[\d{1,3}\]\s*(?:[A-Z\u00C0-\u024F\"\“]))'
        pattern_bracket = r'(?=(?:^|(?<=[\s\.\>\)\]\"\”\’]))\[\s*\d{1,3}\s*\]\s*(?:[A-Z\u00C0-\u024F\"\“]))'
        pattern_dot = r'(?=(?:^|(?<=[\.\s\>\)\]\"\”\’]))\s*\d{1,3}\.\s+(?:[A-Z\u00C0-\u024F\"\“]))'

        expanded = []
        for part in parts:
            b_matches = list(re.finditer(r'(?:^|[\s\.\>\)\]\"\”\’])\[(\d{1,3})\]\s*(?=[A-Z\u00C0-\u024F\"\“])', part))
            part = cls.normalize_bracket_spacing(part)
            b_matches = list(re.finditer(r'(?:^|[\s\.\>\)\]\"\”\’])\[\s*(\d{1,3})\s*\]\s*(?=[A-Z\u00C0-\u024F\"\“])', part))
            if len(b_matches) >= 2:
                sub_parts = re.split(pattern_bracket, part)
                for sp in sub_parts:
                    sp_clean = re.sub(r'\s+', ' ', sp).strip()
                    if len(sp_clean) > 15:
                        expanded.append(sp_clean)
                continue

            d_matches = list(re.finditer(r'(?:^|[\.\s\>\)\]\"\”\’])\s*(\d{1,3})\.\s+(?=[A-Z\u00C0-\u024F\"\“])', part))
            if len(d_matches) >= 2:
                sub_parts = re.split(pattern_dot, part)
                for sp in sub_parts:
                    sp_clean = re.sub(r'\s+', ' ', sp).strip()
                    if len(sp_clean) > 15:
                        expanded.append(sp_clean)
                continue

            expanded.append(part)
        return expanded

    @classmethod
    def split_manuscript_references(cls, references_blob: str) -> List[str]:
        """
        Splits a raw References section from a manuscript (PDF/DOCX) into individual citation strings.
        Handles:
        1. Numbered bracketed items: [1], [2], ...
        2. Numbered dot items: 1., 2., ...
        3. Numbered paren items: (1), (2), ...
        4. Multi-line paragraphs and blank-line separated entries
        5. Composite semicolon delimited fallback
        """
        if not references_blob or not references_blob.strip():
            return []

        # Sanitize any embedded ASCII control characters from PDF streams
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', ' ', references_blob).strip()

        # Normalize kerning / whitespace inside numbered brackets (e.g. '[1 0]' -> '[10]', '[15 ]' -> '[15]')
        text = cls.normalize_bracket_spacing(text)

        # Check 1A: Bracketed numbers e.g. [1], [2] at line starts
        bracket_matches = list(re.finditer(r'(?m)^\s*\[\d+\]\s+', text))
        if len(bracket_matches) >= 2:
            parts = re.split(r'(?m)(?=^\s*\[\d+\]\s+)', text)
            clean_parts = [re.sub(r'\s+', ' ', p).strip() for p in parts if len(p.strip()) > 15]
            if len(clean_parts) >= 2:
                return cls._subsplit_inline_numbered_references(clean_parts)

        # Check 1B: Bracketed numbers anywhere in the text (including inline after soft-wraps without newline)
        inline_bracket_matches = list(re.finditer(r'(?:^|[\s\.\>\)\]\"\”\’])\[(\d{1,3})\]\s*(?=[A-Z\u00C0-\u024F\"\“])', text))
        if len(inline_bracket_matches) >= 2:
            parts = re.split(r'(?=(?:^|(?<=[\s\.\>\)\]\"\”\’]))\[\d{1,3}\]\s*(?:[A-Z\u00C0-\u024F\"\“]))', text)
            clean_parts = [re.sub(r'\s+', ' ', p).strip() for p in parts if len(p.strip()) > 15]
            if len(clean_parts) >= 2:
                return cls._subsplit_inline_numbered_references(clean_parts)

        # Check 2A: Dotted numbers e.g. 1. , 2. at line starts
        dot_matches = list(re.finditer(r'(?m)^\s*\d+\.\s+', text))
        if len(dot_matches) >= 2:
            parts = re.split(r'(?m)(?=^\s*\d+\.\s+)', text)
            clean_parts = [re.sub(r'\s+', ' ', p).strip() for p in parts if len(p.strip()) > 15]
            if len(clean_parts) >= 2:
                return cls._subsplit_inline_numbered_references(clean_parts)

        # Check 2B: Dotted numbers anywhere in the text (e.g. "...doi:xxx 2. Smith" or " 2. Jones")
        inline_dot_matches = list(re.finditer(r'(?:^|(?<=[\.\s\>\)\]\"\”\’]))\s*(\d{1,3})\.\s+(?=[A-Z\u00C0-\u024F\"\“])', text))
        if len(inline_dot_matches) >= 2:
            parts = re.split(r'(?=(?:^|(?<=[\.\s\>\)\]\"\”\’]))\s*\d{1,3}\.\s+(?:[A-Z\u00C0-\u024F\"\“]))', text)
            clean_parts = [re.sub(r'\s+', ' ', p).strip() for p in parts if len(p.strip()) > 15]
            if len(clean_parts) >= 2:
                return cls._subsplit_inline_numbered_references(clean_parts)

        # Check 3: Parenthesized numbers e.g. (1), (2) at line starts
        paren_matches = list(re.finditer(r'(?m)^\s*\(\d+\)\s+', text))
        if len(paren_matches) >= 2:
            parts = re.split(r'(?m)(?=^\s*\(\d+\)\s+)', text)
            clean_parts = [re.sub(r'\s+', ' ', p).strip() for p in parts if len(p.strip()) > 15]
            if len(clean_parts) >= 2:
                return cls._subsplit_inline_numbered_references(clean_parts)

        # Check 4: Unnumbered Author-Date Bibliography Format
        ay_parts = cls._split_author_date_references(text)
        if len(ay_parts) >= 2:
            return ay_parts

        # Check 5: Double-newline separated paragraphs
        para_parts = re.split(r'\n\s*\n+', text)
        clean_paras = [re.sub(r'\s+', ' ', p).strip() for p in para_parts if len(p.strip()) > 20]
        if len(clean_paras) >= 2:
            return cls._subsplit_inline_numbered_references(clean_paras)

        # Check 6: Semicolon separated fallback
        if ";" in text:
            tokens = [t.strip() for t in text.split(";") if len(t.strip()) > 15]
            if len(tokens) >= 2:
                return tokens

        # Fallback: Split by single newline if each line is reasonably long
        lines = [re.sub(r'\s+', ' ', l).strip() for l in text.splitlines() if len(l.strip()) > 25]
        if len(lines) >= 2:
            return lines

        return [re.sub(r'\s+', ' ', text).strip()]

    @classmethod
    def _split_author_date_references(cls, text: str) -> List[str]:
        """
        Splits unnumbered author-date style reference sections (e.g. APA, Harvard, Chicago, Taylor & Francis).
        Accurately detects boundaries between multi-line bibliographic entries.
        """
        clean_lines = []
        for l in text.splitlines():
            l_str = l.strip()
            if not l_str:
                continue
            # Filter running headers/footers e.g. 'JOURNALOFWEBLIBRARIANSHIP 175' or '174 A. VECCHIONE ET AL.'
            if re.match(r'^(?:JOURNAL\s*OF\s*[A-Za-z\s]+|[A-Z\s]{4,}\s+\d{1,4}|\d{1,4}\s+[A-Z\s\.\,\'\-]{4,})$', l_str, re.IGNORECASE):
                continue
            clean_lines.append(l_str)

        entries = []
        current = []

        for l in clean_lines:
            # Pattern A: Standard author name followed by year or n.d.
            is_author_start = bool(re.match(
                r'^[A-Z\u00C0-\u024F][a-zA-Z\u00C0-\u024F\s\.\,\'\-]{1,60}?(?:,\s*|\.\s*|\s+)(?:(?:19|20)\d{2}[a-z]?|n\.d\.[a-z]?|\((?:19|20)\d{2}[a-z]?\))\s*[\.\:\,\)]',
                l
            ))
            # Pattern B: Known corporate authors e.g. Google, WHO, IEEE, NIST, etc.
            is_corporate_start = bool(re.match(
                r'^(?:Google|World\s+Health\s+Organization|National\s+Institutes\s+of\s+Health|IEEE|ACM|APA|ISO|W3C|National\s+Research\s+Council)\b',
                l, re.IGNORECASE
            ))
            # Pattern C: Author surname, Given name without year on first line
            is_author_no_year = bool(re.match(r'^[A-Z\u00C0-\u024F][a-zA-Z\u00C0-\u024F\s\.\,\'\-]{1,40},\s+[A-Z\u00C0-\u024F]', l))

            prev_text = current[-1] if current else ''
            prev_ended = bool(re.search(r'[\.\?\!\"”\’\)\/]\s*$|[a-z0-9]\.html?\s*$|[0-9]{5,}\s*$', prev_text))
            prev_has_doi_or_url = bool(re.search(r'(?:doi\.org\/|http|\.html?|\.php|\d{4}\.\d{4,})', prev_text, re.IGNORECASE))

            if current and (
                (is_author_start and (prev_ended or prev_has_doi_or_url)) or
                (is_corporate_start and (prev_ended or prev_has_doi_or_url)) or
                (is_author_no_year and (prev_ended or prev_has_doi_or_url))
            ):
                entries.append(' '.join(current))
                current = [l]
            else:
                current.append(l)

        if current:
            entries.append(' '.join(current))

        return [re.sub(r'\s+', ' ', e).strip() for e in entries if len(e.strip()) > 15]

    @classmethod
    def split(
        cls,
        references_text: str,
        source_eid: str = "",
        source_title: str = "",
        source_authors: str = "",
        source_year: Optional[int] = None,
        source_doi: str = "",
    ) -> List[ParsedReference]:
        """
        Splits a single composite References string into individual ParsedReference records.
        """
        if not references_text or not references_text.strip():
            return []

        raw_clean = normalize_whitespace(references_text)
        tokens = [t.strip() for t in raw_clean.split(";") if t.strip()]
        if not tokens:
            return []

        parsed_records: List[ParsedReference] = []
        buffer: List[str] = []
        ref_counter = 1

        def flush_buffer(is_remainder: bool = False, extra_reasons: Optional[List[str]] = None) -> None:
            nonlocal ref_counter
            if not buffer:
                return
            ref_str = "; ".join(buffer).strip()
            if not ref_str:
                buffer.clear()
                return

            record = cls._build_reference_record(
                raw_ref=ref_str,
                ref_no=ref_counter,
                source_eid=source_eid,
                source_title=source_title,
                source_authors=source_authors,
                source_year=source_year,
                source_doi=source_doi,
                is_remainder=is_remainder,
                extra_reasons=extra_reasons or [],
            )
            parsed_records.append(record)
            ref_counter += 1
            buffer.clear()

        i = 0
        n = len(tokens)
        while i < n:
            curr_token = tokens[i]
            buffer.append(curr_token)

            # Check 1: Does current token end in a standard parenthesized year: (2020)
            if YEAR_MARKER_END_REGEX.search(curr_token):
                flush_buffer()
                i += 1
                continue

            # Check 2: Does current token contain a parenthesized year followed by a trailing period/char?
            # e.g., "(2019)." or "(2020) pp. 1-10"
            m_year = YEAR_MARKER_ANY_REGEX.search(curr_token)
            if m_year:
                # If there is a next token, and that next token looks like a new author start, flush!
                if i + 1 < n and AUTHOR_START_REGEX.match(tokens[i + 1]):
                    flush_buffer()
                    i += 1
                    continue

            # Check 3: Does current token end with a URL or DOI?
            if re.search(r"(?:https?://\S+|doi:\s*\S+|10\.\d{4,9}/\S+)\s*$", curr_token, re.I):
                # If buffer has substantial length or next token is an author start, flush!
                if i + 1 < n and AUTHOR_START_REGEX.match(tokens[i + 1]):
                    flush_buffer()
                    i += 1
                    continue

            # Check 4: If buffer has accumulated multiple segments without a year marker and next token looks like author start
            if len(buffer) >= 3 and i + 1 < n:
                if AUTHOR_START_REGEX.match(tokens[i + 1]):
                    # Check if buffer has page or journal cues
                    buf_joined = " ".join(buffer)
                    if re.search(r"\b(?:pp\.|pages|vol\.|volume|no\.)\b", buf_joined, re.I):
                        flush_buffer(extra_reasons=["SPLIT_ON_AUTHOR_BOUNDARY_WITHOUT_YEAR"])
                        i += 1
                        continue

            i += 1

        # Any trailing tokens remaining in buffer
        if buffer:
            flush_buffer(is_remainder=True, extra_reasons=["TRAILING_REMAINDER_NO_CLOSING_YEAR"])

        return parsed_records

    @classmethod
    def _build_reference_record(
        cls,
        raw_ref: str,
        ref_no: int,
        source_eid: str,
        source_title: str,
        source_authors: str = "",
        source_year: Optional[int] = None,
        source_doi: str = "",
        is_remainder: bool = False,
        extra_reasons: Optional[List[str]] = None,
    ) -> ParsedReference:
        """
        Constructs a ParsedReference and evaluates diagnostic quality flags.
        """
        reasons = list(extra_reasons or [])
        
        # Year extraction
        year_matches = YEAR_MARKER_ANY_REGEX.findall(raw_ref)
        year_marker_count = len(year_matches)
        detected_year_str = year_matches[-1] if year_matches else ""
        
        cited_year: Optional[int] = None
        if detected_year_str:
            clean_y = re.sub(r"[^\d]", "", detected_year_str)
            if clean_y.isdigit() and 1800 <= int(clean_y) <= 2030:
                cited_year = int(clean_y)
        else:
            # Fallback to any 4-digit year
            all_4d = YEAR_4DIGIT_REGEX.findall(raw_ref)
            if all_4d:
                clean_y = all_4d[-1]
                if 1800 <= int(clean_y) <= 2030:
                    cited_year = int(clean_y)
                    detected_year_str = str(cited_year)

        has_year = cited_year is not None

        # DOI & URL extraction
        extracted_doi = extract_doi(raw_ref) or ""
        extracted_url = extract_url(raw_ref) or ""
        has_doi = bool(extracted_doi)
        has_url = bool(extracted_url)

        # Diagnostics & Review flags
        needs_review = False
        if not has_year:
            needs_review = True
            reasons.append("NO_YEAR_DETECTED")
        if year_marker_count > 1:
            needs_review = True
            reasons.append("MULTIPLE_YEAR_MARKERS")
        if len(raw_ref) > 600:
            needs_review = True
            reasons.append("SUSPICIOUSLY_LONG_REFERENCE")
        elif len(raw_ref) < 25:
            needs_review = True
            reasons.append("SUSPICIOUSLY_SHORT_REFERENCE")
        if is_remainder:
            needs_review = True
            if "TRAILING_REMAINDER_NO_CLOSING_YEAR" not in reasons:
                reasons.append("TRAILING_REMAINDER")

        # Dedup reasons
        reasons = list(dict.fromkeys(reasons))

        return ParsedReference(
            source_eid=source_eid,
            reference_no=ref_no,
            raw_reference=raw_ref,
            source_title=source_title,
            source_authors=source_authors,
            source_year=source_year,
            source_doi=source_doi,
            cited_year=cited_year,
            extracted_doi=extracted_doi,
            extracted_url=extracted_url,
            has_year=has_year,
            has_doi=has_doi,
            has_url=has_url,
            year_marker_count=year_marker_count,
            reference_year_detected=detected_year_str,
            needs_review=needs_review,
            review_reasons=reasons,
        )

