"""
Bibliographic citation field parser.
Decomposes a raw reference string into author, title, journal, volume, issue, pages, and publication year.
Supports Elsevier, IEEE, APA, Harvard, Nature, Vancouver, and Scopus citation formats.
"""
import re
import unicodedata
from typing import Dict, Any, Optional
from src.parsing.normalizer import normalize_whitespace

# Regex for pages: e.g. pp. 751-752, pp. 1-15, 751-752, e57400, 101896
PAGES_REGEX = re.compile(r"\b(?:pp\.?|p\.)\s*([0-9]+(?:\s*[-–—]\s*[0-9]+)?)\b", re.IGNORECASE)

# Regex for volume / issue: e.g. 97, 6, pp. or vol. 43, no. 1 or 3 (4)
VOL_ISSUE_REGEX = re.compile(r"\b(?:vol\.?\s*)?(\d{1,4})\s*(?:,\s*|\s*)\((?:no\.?|issue\s*)?(\d{1,3})\)", re.IGNORECASE)
VOL_COMMA_ISSUE_REGEX = re.compile(r"\b(?:vol\.?\s*)?(\d{1,4})\s*,\s*(?:(?:no\.?|issue)\s*)?(\d{1,3})\b", re.IGNORECASE)

# Common institutional prefixes or words
INSTITUTIONAL_KEYWORDS = {
    "association", "organization", "organisation", "committee", "institute", 
    "society", "council", "academy", "commission", "department", "ministry", 
    "who", "ieee", "acm", "iso", "world health", "united states"
}


def _looks_like_author(seg: str) -> bool:
    """Heuristic check whether a comma-delimited segment represents an author name."""
    s = seg.strip().rstrip(".,;").strip()
    if not s or len(s) > 60:
        return False

    # "et al." or "and colleagues"
    if re.search(r"\bet al\b", s, re.IGNORECASE):
        return True

    # Institutional author
    s_lower = s.lower()
    if any(inst in s_lower for inst in INSTITUTIONAL_KEYWORDS):
        return True

    # Initials followed by Surname: 'Z. Guo', 'A. Lai', 'J.H. Thygesen', 'W.-t. Yih', 'A. d'Avila Garcez', 'N. Díaz-Rodríguez'
    if re.match(r"^[A-Z][\.\-a-zA-Z\u0300-\u036f]*\s+(?:(?:d'|de|del|van|von|da|la)\s+)?[\w\-\'\s\u0300-\u036f]+$", s):
        words = s.split()
        if len(words) <= 5:
            # If it has more than 3 words and many lowercase words, verify it's not a title
            lowercase_words = [w for w in words if w.islower() and w not in ("d'", "de", "del", "van", "von", "da", "la")]
            if len(lowercase_words) <= 1:
                return True

    # Surname followed by initials: 'Guo, Z.', 'Arrieta, A.B.', 'Robertson, S.'
    if re.match(r"^[\w\-\'\u0300-\u036f]+(\s+[A-Z]\.?)+$", s):
        return True

    # Single capitalized surname in author list (e.g. 'Farrington', 'Guo')
    if re.match(r"^[\w\-\'\u0300-\u036f]+$", s) and len(s) < 25 and s[0].isupper():
        return True

    return False


class CitationParser:
    """
    Extracts bibliographic fields from parsed reference strings.
    """

    @classmethod
    def parse(cls, raw_reference: str) -> Dict[str, Any]:
        """
        Parses raw_reference into author, title, journal, volume, issue, pages, and year.
        """
        if not raw_reference:
            return {
                "cited_authors": "",
                "cited_title": "",
                "cited_journal": "",
                "cited_volume": "",
                "cited_issue": "",
                "cited_pages": "",
                "cited_year": None,
            }

        # Normalize unicode NFKC to convert ligatures (ff, fi, etc.) and non-standard hyphens
        ref = unicodedata.normalize("NFKC", raw_reference)
        ref = normalize_whitespace(ref).strip()

        result: Dict[str, Any] = {
            "cited_authors": "",
            "cited_title": "",
            "cited_journal": "",
            "cited_volume": "",
            "cited_issue": "",
            "cited_pages": "",
            "cited_year": None,
        }

        # 1. Strip leading reference number/bracket: e.g. [1], [ 10 ], 1., (1)
        clean = re.sub(r"^\s*\[\s*\d+\s*\]\s*|^\s*\(\s*\d+\s*\)\s*|^\s*\d+[\.\)]\s*", "", ref).strip()

        # 2. Extract Year: search for 4 digits (1800-2099)
        # Prefer parenthesized year e.g. (2024) or (2020)
        m_paren_year = re.search(r"\(\s*((?:18|19|20)\d{2})[a-z]?\s*\)", clean)
        if m_paren_year:
            result["cited_year"] = int(m_paren_year.group(1))
        else:
            m_year = re.search(r"\b((?:18|19|20)\d{2})\b", clean)
            if m_year:
                result["cited_year"] = int(m_year.group(1))

        # 3. Extract Pages & Article Numbers
        m_pages = PAGES_REGEX.search(clean)
        if m_pages:
            result["cited_pages"] = m_pages.group(1).replace(" ", "")
        else:
            # Check for range pattern like 82-115 or 333-389 at the end
            m_range = re.search(r"\b(\d{1,5}\s*[-–—]\s*\d{1,5})\b", clean)
            if m_range:
                result["cited_pages"] = m_range.group(1).replace(" ", "")
            else:
                # Elsevier article numbers: e.g. e57400, 101896, 103649
                m_art = re.search(r"\b(e\d{4,8}|\d{5,8})\.?$", clean)
                if m_art:
                    result["cited_pages"] = m_art.group(1)

        # 4. Extract Volume & Issue
        m_vol = VOL_ISSUE_REGEX.search(clean)
        if m_vol:
            result["cited_volume"] = m_vol.group(1)
            result["cited_issue"] = m_vol.group(2)
        else:
            m_vol_comma = VOL_COMMA_ISSUE_REGEX.search(clean)
            if m_vol_comma:
                result["cited_volume"] = m_vol_comma.group(1)
                result["cited_issue"] = m_vol_comma.group(2)
            else:
                m_vol_yr = re.search(r"\b(\d{1,4})\s*\(\s*(?:18|19|20)\d{2}[a-z]?\s*\)", clean)
                if m_vol_yr:
                    result["cited_volume"] = m_vol_yr.group(1)

        # 5. Format-Specific Decomposition
        # Case A: Title enclosed in quotation marks: e.g. Authors, "Title of paper", Venue
        m_quote = re.search(r'[\"“](.*?)[\"”]', clean)
        if m_quote:
            result["cited_title"] = m_quote.group(1).strip()
            raw_authors = clean[:m_quote.start()].strip().rstrip(",;.")
            # Strip trailing year if embedded before title: e.g. "Barba, Ian, ... 2013." -> "Barba, Ian, ..."
            raw_authors = re.sub(r'[\.\,\s]+(?:(?:18|19|20)\d{2}[a-z]?|n\.d\.[a-z]?)\s*[\.\,]?\s*$', '', raw_authors).strip()
            result["cited_authors"] = raw_authors.rstrip(",;.")
            after_quote = clean[m_quote.end():].strip().lstrip(",;. ")
            result["cited_journal"] = after_quote.rstrip(",;.")
            return result

        # Case B: APA Style: Authors (Year). Title. Venue.
        pat_apa = re.compile(r"^(.*?)\s*\(((?:18|19|20)\d{2}[a-z]?)\)\.\s+([A-Z].*)$")
        m_apa = pat_apa.match(clean)
        if m_apa and len(m_apa.group(1)) > 3:
            result["cited_authors"] = m_apa.group(1).strip()
            result["cited_year"] = int(m_apa.group(2)[:4])
            rest = m_apa.group(3).strip()
            parts = re.split(r"\.\s+", rest, maxsplit=1)
            result["cited_title"] = parts[0].strip()
            if len(parts) > 1:
                result["cited_journal"] = parts[1].strip().rstrip(",;.")
            return result

        # Case B2: Author-Date without parentheses: Authors. Year. Title. Venue / URLs.
        pat_ay_dot = re.compile(r"^([A-Z\u00C0-\u024F][a-zA-Z\u00C0-\u024F\s\.\,\'\-]{1,60}?)\s*(?:\.\s*|\,\s*)((?:18|19|20)\d{2}[a-z]?|n\.d\.[a-z]?)\.?\s*([A-Z].*)$")
        m_ay_dot = pat_ay_dot.match(clean)
        if m_ay_dot and len(m_ay_dot.group(1)) > 2:
            result["cited_authors"] = m_ay_dot.group(1).strip().rstrip(",;.")
            yr_str = m_ay_dot.group(2).strip()
            if yr_str[:4].isdigit():
                result["cited_year"] = int(yr_str[:4])
            rest = m_ay_dot.group(3).strip()
            parts = re.split(r"\.\s+", rest, maxsplit=1)
            result["cited_title"] = parts[0].strip()
            if len(parts) > 1:
                result["cited_journal"] = parts[1].strip().rstrip(",;.")
            return result

        # Case C: Scopus Semicolon Author Format: Author A.; Author B., Title, Venue (Year)
        if ";" in clean:
            parts = clean.split(",", 1)
            if ";" in parts[0]:
                result["cited_authors"] = parts[0].strip()
                remainder = parts[1].strip() if len(parts) > 1 else ""
                sub = remainder.split(",", 1)
                result["cited_title"] = sub[0].strip()
                if len(sub) > 1:
                    result["cited_journal"] = sub[1].strip().rstrip(",;.")
                return result

        # Case D: "et al." delimiter in author list
        m_etal = re.search(r"^(.*?\bet al\b\.?),\s+(.*)$", clean, re.IGNORECASE)
        if m_etal:
            result["cited_authors"] = m_etal.group(1).strip()
            rest = m_etal.group(2).strip()
            # Split rest into title and venue
            # Check for conference prefix: in: Proceedings...
            in_split = re.split(r",\s*(?:in|In):\s*", rest, maxsplit=1)
            if len(in_split) > 1:
                result["cited_title"] = in_split[0].strip()
                result["cited_journal"] = f"in: {in_split[1].strip().rstrip(',;.')}"
            else:
                parts = [p.strip() for p in rest.split(",") if p.strip()]
                if len(parts) >= 2:
                    result["cited_title"] = parts[0]
                    result["cited_journal"] = ", ".join(parts[1:]).rstrip(",;.")
                else:
                    result["cited_title"] = rest.rstrip(",;.")
            return result

        # Case E: Standard Comma-Separated Academic Format (Elsevier / IEEE / Vancouver)
        in_split = re.split(r",\s*(?:in|In):\s*", clean, maxsplit=1)
        before_in = in_split[0]
        venue_tail = in_split[1] if len(in_split) > 1 else ""

        segments = [p.strip() for p in before_in.split(",") if p.strip()]
        author_parts = []
        title_parts = []
        found_title = False

        for seg in segments:
            if not found_title:
                if _looks_like_author(seg):
                    author_parts.append(seg)
                else:
                    found_title = True
                    title_parts.append(seg)
            else:
                title_parts.append(seg)

        result["cited_authors"] = ", ".join(author_parts)

        if title_parts:
            if venue_tail:
                result["cited_title"] = ", ".join(title_parts)
                result["cited_journal"] = f"in: {venue_tail.strip().rstrip(',;.')}"
            else:
                # If 2 or more segments, the last segment typically holds journal/volume/year
                if len(title_parts) >= 2 and any(char.isdigit() for char in title_parts[-1]):
                    result["cited_title"] = ", ".join(title_parts[:-1])
                    result["cited_journal"] = title_parts[-1].rstrip(",;.")
                else:
                    result["cited_title"] = title_parts[0]
                    if len(title_parts) > 1:
                        result["cited_journal"] = ", ".join(title_parts[1:]).rstrip(",;.")
        else:
            result["cited_title"] = clean

        # LLM fallback for ambiguous or failed heuristic parsing
        from config import ENABLE_LLM_FALLBACK
        if ENABLE_LLM_FALLBACK:
            title_len = len(result.get("cited_title") or "")
            authors_len = len(result.get("cited_authors") or "")
            if title_len < 10 or authors_len == 0 or result.get("cited_title") == clean:
                try:
                    from src.llm.citation_extractor import LLMCitationExtractor
                    from src.llm.client import LLMClient
                    client = LLMClient.get_default()
                    if client.is_available():
                        llm_parsed = LLMCitationExtractor(client).parse(raw_reference)
                        if llm_parsed.get("cited_title") and len(llm_parsed["cited_title"]) >= 10:
                            for k in ("cited_authors", "cited_title", "cited_journal", "cited_year", "cited_volume", "cited_issue", "cited_pages"):
                                if llm_parsed.get(k):
                                    result[k] = llm_parsed[k]
                except Exception:
                    pass

        return result
