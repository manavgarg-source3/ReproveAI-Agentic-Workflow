"""
DOI and URL extraction and canonical normalization.
"""
import re
from typing import Optional, Tuple

# Comprehensive regex for DOI
DOI_REGEX = re.compile(
    r"\b(?:doi:\s*|https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)",
    re.IGNORECASE,
)

# Regex to detect general URLs
URL_REGEX = re.compile(
    r"https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)",
    re.IGNORECASE,
)


def extract_ocr_tolerant_doi(text: str) -> Optional[str]:
    """
    Fallback extractor for DOIs affected by PDF font substitution or OCR kerning:
    - Letter 'l' or 'I' substituted for '1': e.g. 'doi:l0.5430', 'doi:I0.1016'
    - Internal spaces introduced into prefixes and paths: e.g. '10. 1 080/1 533', 'LM-04- 2021-0055'
    - Letters confused after volume/issue markers: e.g. 'v4nl' -> 'v4n1', 'pl2' -> 'p12'
    """
    if not text:
        return None

    # Match candidate starting with doi: or 10. or l0. or I0.
    m = re.search(
        r'(?:doi(?::|\.org/)\s*|https?://[^\s]*doi\.org/|\b(?:10|l0|I0|lo)\s*\.\s*)([^\r\n]+)',
        text,
        re.IGNORECASE
    )
    if not m:
        return None

    raw = m.group(0)
    cand = re.sub(r'^(?:https?://[^\s]*doi\.org/|doi:\s*)', '', raw, flags=re.IGNORECASE)
    cand = re.sub(r'^(?:10|l0|I0|lo)\s*\.\s*', '10.', cand, flags=re.IGNORECASE)
    cand = re.split(r'\s+(?:Authorized|Available|Downloaded|http|Retrieved)\b', cand, flags=re.IGNORECASE)[0]
    cand = re.sub(r'\s+\d{1,4}\s*$', '', cand)

    if '/' not in cand:
        return None

    prefix, _, suffix = cand.partition('/')
    prefix = re.sub(r'\s+', '', prefix)
    prefix = prefix.replace('l', '1').replace('I', '1').replace('O', '0')
    suffix = re.sub(r'\s+', '', suffix)

    # Common OCR letter/digit confusions in suffix after 'p', 'v', 'n' (e.g. v4nl -> v4n1, pl2 -> p12)
    suffix = re.sub(r'([vpn]\d*)l(?=[a-z\d]|\b)', r'\g<1>1', suffix)

    cand = f'{prefix}/{suffix}'
    cand = cand.rstrip('.,;:) ]}')
    m_doi = re.search(r'\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)', cand)
    if m_doi:
        return normalize_doi(m_doi.group(1))
    return None


import unicodedata
from typing import Optional, Tuple, List


def extract_doi(text: str) -> Optional[str]:
    """
    Extracts the first valid DOI from a text string and returns it normalized to canonical 10.xxxx/yyyy format.
    Returns None if no DOI is found.
    """
    if not text:
        return None

    # Normalize unicode NFKC to convert ligatures (ff -> ff, etc.)
    norm_text = unicodedata.normalize("NFKC", text)

    match = DOI_REGEX.search(norm_text)
    if match:
        doi = match.group(1)
        normalized = normalize_doi(doi)
        if normalized:
            return normalized

    # Fallback to OCR-tolerant extraction
    return extract_ocr_tolerant_doi(norm_text)


def extract_document_doi(text: str, links: Optional[List[str]] = None) -> Optional[str]:
    """
    Detects the primary manuscript DOI from Page 1 / header text and embedded PDF links.
    """
    # 1. Check embedded annotation links first
    if links:
        for link in links:
            if "doi.org/10." in link.lower() or "10." in link:
                cand = extract_doi(link)
                if cand:
                    return cand

    # 2. Check early document text (first 5,000 characters)
    if text:
        norm_text = unicodedata.normalize("NFKC", text[:5000])
        # Direct regex search
        matches = DOI_REGEX.findall(norm_text)
        for m in matches:
            norm = normalize_doi(m)
            if norm:
                return norm

        # Fallback OCR-tolerant search on early text
        cand = extract_ocr_tolerant_doi(norm_text)
        if cand:
            return cand

    return None


def normalize_doi(doi: str) -> Optional[str]:
    """
    Canonicalizes a DOI:
    - Removes URL prefix or 'doi:' scheme
    - Trims whitespace
    - Strips trailing punctuation (.,;) unless part of balanced parentheses
    - Lowercases the directory prefix '10.xxxx/'
    """
    if not doi:
        return None

    doi = doi.strip()
    
    # Strip URL and doi: prefixes
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)
    
    # Strip trailing punctuation common in bibliographic references: .,;,)]
    while doi and doi[-1] in ".,;: \t\n\r":
        doi = doi[:-1]
        
    # Balanced parenthesis check: if trailing closing parenthesis has no opening counterpart, strip it
    if doi.endswith(")") and doi.count("(") < doi.count(")"):
        doi = doi[:-1]
    if doi.endswith("]") and doi.count("[") < doi.count("]"):
        doi = doi[:-1]

    # Validate syntax: must start with 10. and contain slash
    if not re.match(r"^10\.\d{4,9}/.+", doi):
        return None

    # Lowercase authority prefix (e.g., 10.1000/) while preserving suffix
    parts = doi.split("/", 1)
    prefix = parts[0].lower()
    suffix = parts[1]
    return f"{prefix}/{suffix}"


def extract_url(text: str) -> Optional[str]:
    """
    Extracts the first non-DOI web URL found in text.
    """
    if not text:
        return None

    matches = URL_REGEX.findall(text)
    for u in matches:
        if "doi.org" not in u.lower():
            # Clean trailing punctuation
            u_clean = u.rstrip(".,;)")
            return u_clean
    return None

