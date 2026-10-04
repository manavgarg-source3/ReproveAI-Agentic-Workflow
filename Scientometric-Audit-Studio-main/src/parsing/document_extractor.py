"""
Document Extractor Engine for PDF and DOCX Research Papers.
Extracts textual content, pages, headings, and metadata from academic manuscripts
with layout awareness, header/footer filtering, and scanned-PDF detection.
"""
import io
import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

import pypdf
import docx

logger = logging.getLogger(__name__)


@dataclass
class DocumentContent:
    filename: str
    file_type: str  # 'pdf' or 'docx'
    full_text: str
    pages: List[str] = field(default_factory=list)
    page_count: int = 0
    word_count: int = 0
    char_count: int = 0
    estimated_title: str = ""
    is_scanned: bool = False
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    links: List[str] = field(default_factory=list)
    detected_doi: str = ""


def clean_control_characters(text: str) -> str:
    """
    Strips non-printable ASCII control characters (such as form-feed \x0c, null \x00,
    vertical tab \x0b, etc.) that corrupt XML/Excel documents and cause openpyxl crashes.
    Retains standard whitespace: tab (\t), newline (\n), carriage return (\r).
    """
    if not text:
        return ""
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', ' ', text)


def clean_line_hyphenation(text: str) -> str:
    """
    De-hyphenates words split across line breaks (e.g., 'bio-\ntechnology' -> 'biotechnology'),
    while preserving intentional hyphens and DOI structures.
    """
    if not text:
        return ""
    cleaned = clean_control_characters(text)
    # Pattern: word ending with hyphen at line end, followed by word characters on next line
    cleaned = re.sub(r'([A-Za-z]{2,})-\s*\n\s*([A-Za-z]{2,})', r'\1\2', cleaned)
    return cleaned


def filter_running_headers_footers(page_texts: List[str]) -> List[str]:
    """
    Filters out recurring headers and footers across pages (e.g. running journal title,
    page numbers, copyright notices).
    """
    if len(page_texts) < 3:
        return page_texts

    # Find candidate first and last lines on each page
    first_lines = []
    last_lines = []
    for pt in page_texts:
        lines = [line.strip() for line in pt.splitlines() if line.strip()]
        if lines:
            first_lines.append(lines[0])
            last_lines.append(lines[-1])

    # Detect lines that appear identically or nearly identically on >= 50% of pages
    header_candidates = set()
    footer_candidates = set()
    threshold = max(2, len(page_texts) // 2)

    for line in first_lines:
        if sum(1 for fl in first_lines if fl == line) >= threshold:
            header_candidates.add(line)
    for line in last_lines:
        if sum(1 for ll in last_lines if ll == line) >= threshold:
            footer_candidates.add(line)

    filtered_pages = []
    for pt in page_texts:
        lines = pt.splitlines()
        clean_lines = []
        for l in lines:
            s = l.strip()
            # Check if line matches common page number patterns like "Page 1 of 12" or single digit
            if re.match(r'^(page\s+\d+(\s+of\s+\d+)?|\d+)$', s, re.IGNORECASE):
                continue
            # Filter publisher watermarks / download footers
            if re.search(r'Authorized licensed use limited to:|Downloaded on [A-Za-z]+ \d+,\s*\d{4}|from IEEE Xplore\. Restrictions apply', s, re.IGNORECASE):
                continue
            if s in header_candidates or s in footer_candidates:
                continue
            clean_lines.append(l)
        filtered_pages.append("\n".join(clean_lines))

    return filtered_pages


def extract_text_from_pdf(file_bytes: bytes, filename: str = "manuscript.pdf") -> DocumentContent:
    """
    Extracts text from a PDF manuscript using pypdf.
    Uses stream-based extraction as primary to maintain multi-column reading order
    (crucial for 2-column IEEE/ACM papers), with layout fallback and de-hyphenation.
    """
    stream = io.BytesIO(file_bytes)
    reader = pypdf.PdfReader(stream)
    page_count = len(reader.pages)
    warnings = []

    page_texts = []
    links = []

    for idx, page in enumerate(reader.pages):
        t = ""
        try:
            # Primary: stream extraction preserves natural column reading flow
            t = page.extract_text()
        except Exception as e:
            logger.warning(f"Stream extraction failed for page {idx+1}: {e}")

        # Fallback: if stream extraction is empty or near-empty, attempt layout mode
        if not t or len(t.strip()) < 20:
            try:
                t = page.extract_text(extraction_mode="layout")
            except Exception as e:
                logger.warning(f"Layout extraction failed for page {idx+1}: {e}")
                t = t or ""

        # Extract annotation links (/Annots)
        if "/Annots" in page:
            try:
                annots = page["/Annots"]
                for a in annots:
                    obj = a.get_object()
                    if "/A" in obj and "/URI" in obj["/A"]:
                        uri = str(obj["/A"]["/URI"]).strip()
                        if uri and uri not in links:
                            links.append(uri)
            except Exception:
                pass

        page_texts.append(t or "")

    # Clean running headers and footers
    filtered_pages = filter_running_headers_footers(page_texts)
    # Apply NFKC normalization across all page texts to fix ligatures
    import unicodedata
    from src.parsing.doi_extractor import extract_document_doi
    filtered_pages = [unicodedata.normalize("NFKC", p) for p in filtered_pages]
    combined_raw = "\n\n".join(filtered_pages)
    cleaned_text = clean_line_hyphenation(combined_raw)
    cleaned_text = unicodedata.normalize("NFKC", cleaned_text)

    char_count = len(cleaned_text.strip())
    word_count = len(cleaned_text.split())

    # Check for scanned or image-only PDF
    is_scanned = False
    if page_count > 0 and (char_count / max(1, page_count)) < 40:
        is_scanned = True
        warnings.append("Document appears to be a scanned image-only PDF with minimal extractable text.")

    # Estimate paper title from the first non-empty lines
    estimated_title = ""
    if filtered_pages:
        p1_lines = [l.strip() for l in filtered_pages[0].splitlines() if l.strip()]
        for line in p1_lines[:6]:
            if len(line) > 15 and not re.match(r'^(https?://|doi:|issn:|volume|page|\d+)', line, re.IGNORECASE):
                estimated_title = line
                break

    meta = {}
    if reader.metadata:
        try:
            meta = {str(k): str(v) for k, v in reader.metadata.items()}
            if "/Title" in meta and meta["/Title"].strip() and len(meta["/Title"].strip()) > 5:
                estimated_title = meta["/Title"].strip()
        except Exception:
            pass

    detected_doi = extract_document_doi(cleaned_text, links=links) or ""

    return DocumentContent(
        filename=filename,
        file_type="pdf",
        full_text=cleaned_text,
        pages=filtered_pages,
        page_count=page_count,
        word_count=word_count,
        char_count=char_count,
        estimated_title=estimated_title,
        is_scanned=is_scanned,
        warnings=warnings,
        metadata=meta,
        links=links,
        detected_doi=detected_doi,
    )


def extract_text_from_docx(file_bytes: bytes, filename: str = "manuscript.docx") -> DocumentContent:
    """
    Extracts text from a Word (.docx) document, handling paragraph hierarchy,
    native Word XML list numbering (w:numPr), tables, and footnotes.
    """
    stream = io.BytesIO(file_bytes)
    doc = docx.Document(stream)
    warnings = []

    paragraph_lines = []
    list_counter = 1

    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue

        # Check if this paragraph has native Word list numbering (w:numPr)
        is_list_item = False
        try:
            numPr = p._element.xpath('.//w:numPr')
            if numPr:
                is_list_item = True
        except Exception:
            pass

        # If it's a list item and doesn't already start with a number like "[1]" or "1.", prefix it
        if is_list_item and not re.match(r'^(\[\d+\]|\(?\d+[\.\)])', text):
            text = f"[{list_counter}] {text}"
            list_counter += 1
        elif re.match(r'^(\[\d+\]|\(?\d+[\.\)])', text):
            list_counter += 1

        paragraph_lines.append(text)

    # Extract tables if any (some templates format references or data in tables)
    for table in doc.tables:
        for row in table.rows:
            row_texts = [c.text.strip() for c in row.cells if c.text.strip()]
            if row_texts:
                paragraph_lines.append(" | ".join(row_texts))

    # Extract footnotes if present
    try:
        if hasattr(doc, 'part') and hasattr(doc.part, 'related_parts'):
            for rel in doc.part.related_parts.values():
                if "footnotes" in rel.partname or "endnotes" in rel.partname:
                    fn_tree = rel._element
                    for fn_elem in fn_tree.xpath('.//w:p'):
                        fn_text = "".join(fn_elem.xpath('.//w:t/text()')).strip()
                        if fn_text:
                            paragraph_lines.append(f"[Footnote] {fn_text}")
    except Exception as e:
        logger.debug(f"Footnote extraction note: {e}")

    full_text = "\n\n".join(paragraph_lines)
    cleaned_text = clean_line_hyphenation(full_text)

    char_count = len(cleaned_text.strip())
    word_count = len(cleaned_text.split())

    # Estimate title from first non-empty paragraph or doc properties
    estimated_title = ""
    for line in paragraph_lines[:5]:
        if len(line) > 15 and not re.match(r'^(abstract|keywords|table|figure)', line, re.IGNORECASE):
            estimated_title = line
            break

    try:
        cp = doc.core_properties
        if cp.title and cp.title.strip():
            estimated_title = cp.title.strip()
    except Exception:
        pass

    # Approximate page count (~450 words per academic page)
    approx_pages = max(1, (word_count + 449) // 450)

    return DocumentContent(
        filename=filename,
        file_type="docx",
        full_text=cleaned_text,
        pages=[cleaned_text],  # DOCX is paragraph-stream based
        page_count=approx_pages,
        word_count=word_count,
        char_count=char_count,
        estimated_title=estimated_title,
        is_scanned=False,
        warnings=warnings,
        metadata={}
    )


def extract_document(file_bytes: bytes, filename: str) -> DocumentContent:
    """
    Unified entry point to extract text and structure from a PDF or DOCX file.
    """
    lower = filename.lower()
    if lower.endswith(".pdf"):
        doc = extract_text_from_pdf(file_bytes, filename=filename)
    elif lower.endswith(".docx") or lower.endswith(".doc"):
        doc = extract_text_from_docx(file_bytes, filename=filename)
    else:
        # Fallback to plain text decode
        try:
            text = file_bytes.decode("utf-8-sig", errors="replace")
            words = len(text.split())
            doc = DocumentContent(
                filename=filename,
                file_type="txt",
                full_text=text,
                pages=[text],
                page_count=max(1, (words + 449) // 450),
                word_count=words,
                char_count=len(text)
            )
        except Exception as e:
            raise ValueError(f"Unsupported document format '{filename}': {e}")

    # Ensure all extracted text is clean of illegal XML control characters
    doc.full_text = clean_control_characters(doc.full_text)
    doc.pages = [clean_control_characters(p) for p in doc.pages]
    doc.estimated_title = clean_control_characters(doc.estimated_title)
    return doc

