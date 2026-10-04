"""Safe, in-memory PDF text extraction."""

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class PdfExtractionError(ValueError):
    """Raised when a PDF cannot be read or contains no extractable text."""


@dataclass(frozen=True, slots=True)
class ExtractedPdf:
    text: str
    page_count: int
    pages: tuple[str, ...] = ()

    @property
    def character_count(self) -> int:
        return len(self.text)


def extract_pdf_text(content: bytes) -> ExtractedPdf:
    if not content:
        raise PdfExtractionError("The uploaded PDF is empty.")

    try:
        reader = PdfReader(BytesIO(content), strict=False)
        if reader.is_encrypted:
            try:
                unlocked = reader.decrypt("")
            except Exception as exc:  # pypdf raises several encryption errors
                raise PdfExtractionError("The PDF is password-protected.") from exc
            if not unlocked:
                raise PdfExtractionError("The PDF is password-protected.")

        if not reader.pages:
            raise PdfExtractionError("The PDF contains no pages.")

        page_text = [(page.extract_text() or "").strip() for page in reader.pages]
    except PdfExtractionError:
        raise
    except (PdfReadError, OSError, ValueError, TypeError) as exc:
        raise PdfExtractionError("The PDF could not be read.") from exc
    except Exception as exc:  # Normalize library-specific page/content failures.
        raise PdfExtractionError("Text extraction failed for this PDF.") from exc

    text = "\n\n".join(part for part in page_text if part).strip()
    if not text:
        raise PdfExtractionError(
            "No text could be extracted. The PDF may contain only scanned images."
        )

    return ExtractedPdf(
        text=text,
        page_count=len(reader.pages),
        pages=tuple(page_text),
    )
