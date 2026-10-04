"""
Output writers for CSV and multi-sheet styled Excel reports.
Directly uses openpyxl without pandas dependency to ensure zero C-extension DLL issues.
"""
import csv
import logging
from pathlib import Path
from typing import List, Dict, Any
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from src.models.document import SourceDocument
from src.models.verification import VerificationResult, FinalStatus

logger = logging.getLogger(__name__)


def write_results_csv(results: List[VerificationResult], output_path: Path) -> None:
    """Exports verification results to CSV."""
    if not results:
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(results[0].to_dict().keys())
    with open(output_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r.to_dict())
    logger.info(f"Wrote {len(results)} validation rows to {output_path}")


def write_summary_csv(stats: Dict[str, Any], output_path: Path) -> None:
    """Exports summary KPI metrics to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Metric", "Value"])
        for k, v in stats.items():
            writer.writerow([k, v])
    logger.info(f"Wrote summary metrics to {output_path}")


def write_excel_report(
    documents: List[SourceDocument],
    results: List[VerificationResult],
    stats: Dict[str, Any],
    excel_path: Path,
) -> None:
    """
    Generates a professional multi-sheet Excel workbook with styled headers and status highlights.
    Uses openpyxl natively.
    """
    excel_path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()

    # Styling definitions
    header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    regular_font = Font(name="Segoe UI", size=10)
    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")

    thin_border = Border(
        left=Side(style="thin", color="D3D3D3"),
        right=Side(style="thin", color="D3D3D3"),
        top=Side(style="thin", color="D3D3D3"),
        bottom=Side(style="thin", color="D3D3D3"),
    )

    def style_sheet(ws):
        ws.views.sheetView[0].showGridLines = True
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_align
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.font = regular_font
                cell.border = thin_border
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or "")
                if len(val_str) > max_len:
                    max_len = len(val_str)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 14), 65)

    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

    def sanitize_val(v: Any) -> Any:
        if v is None:
            return ""
        if isinstance(v, str):
            return ILLEGAL_CHARACTERS_RE.sub("", v)
        return v

    def safe_append(ws, row_data):
        ws.append([sanitize_val(c) for c in row_data])

    # 1. Sheet: Summary
    ws_summary = wb.active
    ws_summary.title = "Summary"
    safe_append(ws_summary, ["Metric", "Value"])
    for k, v in stats.items():
        safe_append(ws_summary, [k, v])
    style_sheet(ws_summary)

    # 2. Sheet: Documents
    ws_docs = wb.create_sheet(title="Documents")
    safe_append(ws_docs, ["EID", "Title", "Year", "Source Title", "DOI", "Parsed References", "Link"])
    for d in documents:
        safe_append(ws_docs, [d.eid, d.title, d.year, d.source_title, d.doi, d.parsed_reference_count, d.link])
    style_sheet(ws_docs)

    # 3. Sheet: All_References
    if results:
        ws_refs = wb.create_sheet(title="All_References")
        headers = list(results[0].to_dict().keys())
        safe_append(ws_refs, headers)
        for r in results:
            safe_append(ws_refs, list(r.to_dict().values()))
        style_sheet(ws_refs)

    # 4. Sheet: Human_Review
    review_results = [r for r in results if r.needs_human_review]
    if review_results:
        ws_rev = wb.create_sheet(title="Human_Review")
        headers = list(review_results[0].to_dict().keys())
        safe_append(ws_rev, headers)
        for r in review_results:
            safe_append(ws_rev, list(r.to_dict().values()))
        style_sheet(ws_rev)

    # 5. Sheet: Wrong_DOI_Cases
    wrong_doi_results = [r for r in results if r.final_status == FinalStatus.VALID_DOI_WRONG_REFERENCE]
    if wrong_doi_results:
        ws_wrong = wb.create_sheet(title="Wrong_DOI_Cases")
        headers = list(wrong_doi_results[0].to_dict().keys())
        safe_append(ws_wrong, headers)
        for r in wrong_doi_results:
            safe_append(ws_wrong, list(r.to_dict().values()))
        style_sheet(ws_wrong)

    wb.save(str(excel_path))
    logger.info(f"Successfully generated multi-sheet Excel workbook at {excel_path}")

