"""
Section Segmentation and Boundary Detection Engine.
Isolates the manuscript body text and the bibliography / references section,
while stripping trailing appendices, author biographies, and acknowledgments.
"""
import re
import logging
from typing import Tuple, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Standard academic reference section headings
REFERENCE_HEADING_PATTERNS = [
    # Standalone line with optional Roman/Arabic section number
    r'(?im)^\s*(?:(?:Section\s+)?[0-9IVXLCDM]+\.?\s*)?(?:References|Bibliography|Works Cited|Literature Cited|References and Notes|Reference List)\s*$',
    # Bold / inline style followed by newline or colon
    r'(?im)\n\s*(?:(?:Section\s+)?[0-9IVXLCDM]+\.?\s*)?(?:References|Bibliography|Works Cited|Literature Cited|References and Notes|Reference List)\s*[:\n]',
]

# Sections that commonly appear AFTER references and must be stripped from bibliography
TRAILING_SECTION_PATTERNS = [
    r'(?im)^\s*(?:(?:Section\s+)?[0-9IVXLCDM]+\.?\s*)?(?:Appendix|Appendices|Appendix\s+[A-Z0-9]+)\b',
    # PDF small-caps can be extracted as ``A L ARGE ...`` or ``B I NFERENCE ...``.
    # The leading letter is the appendix label, so it ends the bibliography.
    r'(?m)^\s*[A-Z]\s+[A-Z]\s*[A-Z]{2,}(?:\s+[A-Z][A-Z]+){1,}\s*$',
    r'(?im)^\s*(?:About the Authors?|Author Biographies?|Biographies|Author Information)\b',
    r'(?im)^\s*(?:Author Contributions?|Authors\' Contributions?|Credit Authorship)\b',
    r'(?im)^\s*(?:Acknowledgments?|Acknowledgements?|Funding Information|Financial Disclosure)\b',
    r'(?im)^\s*(?:Declaration of Competing Interests?|Conflict of Interest|Conflicts of Interest)\b',
]


def segment_manuscript(full_text: str) -> Tuple[str, str, Dict[str, Any]]:
    """
    Segments a manuscript's full text into:
    1. body_text: text from the beginning up to the references heading (used for in-text citation auditing)
    2. references_raw_text: text of the bibliography (used for reference extraction and validation)
    3. metadata: dictionary describing the detected heading, split index, and trailing section cutoffs.
    """
    if not full_text or not full_text.strip():
        return "", "", {"found_references_heading": False}

    text_len = len(full_text)
    # Positional heuristic: References rarely start before 30% of an academic paper
    min_search_pos = int(text_len * 0.30)
    search_window = full_text[min_search_pos:]

    best_match = None
    best_heading_text = ""

    for pattern in REFERENCE_HEADING_PATTERNS:
        matches = list(re.finditer(pattern, search_window))
        if matches:
            # Prefer the earliest match in the latter half of the document
            m = matches[0]
            best_match = m
            best_heading_text = m.group(0).strip()
            break

    if best_match:
        split_pos = min_search_pos + best_match.start()
        heading_end_pos = min_search_pos + best_match.end()

        body_text = full_text[:split_pos].strip()
        raw_refs_blob = full_text[heading_end_pos:].strip()

        # Check for trailing sections to strip from the references section
        trailing_cutoff = None
        trailing_section_name = ""

        for t_pattern in TRAILING_SECTION_PATTERNS:
            t_match = re.search(t_pattern, raw_refs_blob)
            if t_match:
                if trailing_cutoff is None or t_match.start() < trailing_cutoff:
                    trailing_cutoff = t_match.start()
                    trailing_section_name = t_match.group(0).strip()

        if trailing_cutoff is not None and trailing_cutoff > 100:
            logger.info(f"Stripping trailing section '{trailing_section_name}' at pos {trailing_cutoff}")
            raw_refs_blob = raw_refs_blob[:trailing_cutoff].strip()

        meta = {
            "found_references_heading": True,
            "heading_text": best_heading_text,
            "split_char_offset": split_pos,
            "trailing_section_stripped": bool(trailing_section_name),
            "trailing_section_name": trailing_section_name,
            "body_word_count": len(body_text.split()),
            "references_raw_chars": len(raw_refs_blob)
        }
        return body_text, raw_refs_blob, meta

    # Fallback heuristic: If no explicit heading found, search for a cluster of citations [1], [2] in last 30%
    last_portion = full_text[int(text_len * 0.70):]
    numbered_seq_match = re.search(r'(?m)^\s*\[1\]\s+[A-Z]', last_portion)
    if not numbered_seq_match:
        numbered_seq_match = re.search(r'(?m)^\s*1\.\s+[A-Z]', last_portion)

    if numbered_seq_match:
        split_pos = int(text_len * 0.70) + numbered_seq_match.start()
        body_text = full_text[:split_pos].strip()
        raw_refs_blob = full_text[split_pos:].strip()
        meta = {
            "found_references_heading": False,
            "fallback_used": "numbered_sequence_clustering",
            "split_char_offset": split_pos,
            "body_word_count": len(body_text.split()),
            "references_raw_chars": len(raw_refs_blob)
        }
        return body_text, raw_refs_blob, meta

    # Complete document fallback: If no boundaries discernible, treat entire text as candidate
    logger.warning("Could not identify distinct References section boundary.")
    return full_text, full_text, {
        "found_references_heading": False,
        "fallback_used": "none",
        "body_word_count": len(full_text.split()),
        "references_raw_chars": len(full_text)
    }

