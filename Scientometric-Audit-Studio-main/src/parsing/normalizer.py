"""
Text and bibliographic normalization utilities.
"""
import re
import unicodedata
from typing import List, Tuple


def normalize_whitespace(text: str) -> str:
    """Collapses consecutive whitespace and trims leading/trailing spaces."""
    if not text:
        return ""
    # Normalize unicode spaces
    text = unicodedata.normalize("NFKD", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_title(title: str) -> str:
    """
    Normalizes article title for robust fuzzy matching:
    - Lowercase
    - Removes punctuation and symbols
    - Collapses spaces
    """
    if not title:
        return ""
    norm = unicodedata.normalize("NFKD", title).lower()
    # Strip HTML tags if present
    norm = re.sub(r"<[^>]+>", " ", norm)
    # Remove punctuation except alphanumeric characters
    norm = re.sub(r"[^\w\s]", " ", norm)
    return normalize_whitespace(norm)


def extract_author_parts(author_raw: str) -> Tuple[str, str]:
    """
    Attempts to extract (surname, initials) from an author string.
    Examples:
      - 'Smith J.' -> ('smith', 'j')
      - 'Smith, John' -> ('smith', 'j')
      - 'J. Smith' -> ('smith', 'j')
      - 'Prathap G.' -> ('prathap', 'g')
    """
    clean = normalize_whitespace(author_raw)
    if not clean:
        return ("", "")
    
    # Remove parenthesized IDs e.g. "Smith, John (12345)"
    clean = re.sub(r"\([^)]*\)", "", clean).strip()
    
    # Check "Surname, Firstname" format
    if "," in clean:
        parts = clean.split(",", 1)
        surname = re.sub(r"[^\w]", "", parts[0]).lower()
        given = parts[1].strip()
        initials = "".join([m.group(0)[0].lower() for m in re.finditer(r"\b\w", given)])
        return (surname, initials)
    
    # Check "Surname Initial." e.g. "Prathap G." or "Kumar H.A."
    m_trailing = re.match(r"^([\w\-]+)\s+([A-Z\.\s]+)$", clean)
    if m_trailing:
        surname = m_trailing.group(1).lower()
        initials = "".join(re.findall(r"[A-Za-z]", m_trailing.group(2))).lower()
        return (surname, initials)
    
    # Check "Initial. Surname" e.g. "G. Prathap" or "N. Díaz-Rodríguez"
    m_leading = re.match(r"^([A-Z\.\s]+)\s+([\w\-]+)$", clean)
    if m_leading:
        surname = m_leading.group(2).lower()
        initials = "".join(re.findall(r"[A-Za-z]", m_leading.group(1))).lower()
        return (surname, initials)

    # Fallback to single word
    tokens = clean.split()
    if len(tokens) == 1:
        return (tokens[0].lower(), "")
    return (tokens[-1].lower(), tokens[0][0].lower())


def normalize_author_list(authors_str: str) -> List[Tuple[str, str]]:
    """
    Parses a concatenated author string into a list of (surname, initial) pairs.
    Handles delimiters: semicolons, commas, 'and', '&'.
    """
    if not authors_str:
        return []

    clean_str = unicodedata.normalize("NFC", unicodedata.normalize("NFKC", authors_str)).strip()
    if ";" in clean_str:
        tokens = [t.strip() for t in clean_str.split(";") if t.strip()]
    elif re.search(r"\band\b|&", clean_str, flags=re.I):
        tokens = [t.strip() for t in re.split(r"\band\b|&", clean_str, flags=re.I) if t.strip()]
    elif "," in clean_str:
        tokens = [t.strip() for t in clean_str.split(",") if t.strip()]
    else:
        tokens = [clean_str]

    results = []
    for t in tokens:
        if t:
            parts = extract_author_parts(t)
            if parts[0]:
                results.append(parts)
    return results

