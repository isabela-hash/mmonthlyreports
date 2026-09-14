"""Google Slides template copying, placeholder replacement, and auditing."""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from tools.report_replacements import TABLE_PLACEHOLDER_TOKENS, build_replacements

PLACEHOLDER_RE = re.compile(r"\{\{[^}]+\}\}")
EMU_PER_INCH = 914400


def _execute_with_retry(request, attempts: int = 3, delay_seconds: float = 1.0):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return request.execute()
        except TimeoutError as exc:
            last_error = exc
            if attempt == attempts:
                raise
            time.sleep(delay_seconds * attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Request execution failed without raising an exception.")


def build_slides_replacements(
    client: str,
    month: str,
    year: int,
    prev_month: str,
    next_month: str,
    kpis: dict,
    insights: dict,
    user_overrides: dict,
    prev_kpis: dict | None = None,
) -> dict[str, str]:
    """Build formatted placeholder replacements for Google Slides."""
    replacements = build_replacements(
        client,
        month,
        year,
        prev_month,
        next_month,
        kpis,
        insights,
        user_overrides,
        prev_kpis=prev_kpis,
    )
    return {key: "" if value is None else str(value) for key, value in replacements.items()}


def copy_presentation(
    drive_service,
    template_presentation_id: str,
    title: str,
    folder_id: str | None = None,
) -> dict[str, str]:
    body: dict[str, Any] = {"name": title}
    if folder_id:
        body["parents"] = [folder_id]
    copied = (
        drive_service.files()
        .copy(
            fileId=template_presentation_id,
            body=body,
            fields="id, name, webViewLink",
        )
    )
    copied = _execute_with_retry(copied)
    return {
        "id": copied["id"],
        "name": copied.get("name", title),
        "webViewLink": copied.get("webViewLink", ""),
    }


def make_replace_all_text_requests(replacements: dict[str, str]) -> list[dict]:
    """Create Slides API replaceAllText requests for every placeholder."""
    return [
        {
            "replaceAllText": {
                "containsText": {"text": placeholder, "matchCase": True},
                "replaceText": value,
            }
        }
        for placeholder, value in sorted(replacements.items())
        if placeholder not in TABLE_PLACEHOLDER_TOKENS
    ]


def replace_placeholders(
    slides_service,
    presentation_id: str,
    replacements: dict[str, str],
    batch_size: int = 100,
) -> int:
    """Replace placeholders and return the total occurrence count reported by Slides."""
    requests = make_replace_all_text_requests(replacements)
    occurrences = 0
    for start in range(0, len(requests), batch_size):
        chunk = requests[start : start + batch_size]
        response = (
            slides_service.presentations()
            .batchUpdate(presentationId=presentation_id, body={"requests": chunk})
        )
        response = _execute_with_retry(response)
        for reply in response.get("replies", []):
            occurrences += reply.get("replaceAllText", {}).get("occurrencesChanged", 0)
    return occurrences


def _collect_text_from_element(element: dict[str, Any], parts: list[str]) -> None:
    shape = element.get("shape", {})
    text = shape.get("text", {})
    for text_element in text.get("textElements", []):
        content = text_element.get("textRun", {}).get("content")
        if content:
            parts.append(content)

    table = element.get("table", {})
    for row in table.get("tableRows", []):
        for cell in row.get("tableCells", []):
            for text_element in cell.get("text", {}).get("textElements", []):
                content = text_element.get("textRun", {}).get("content")
                if content:
                    parts.append(content)

    for child in element.get("elementGroup", {}).get("children", []):
        _collect_text_from_element(child, parts)


def extract_placeholders_from_presentation(presentation: dict[str, Any]) -> set[str]:
    parts: list[str] = []
    for slide in presentation.get("slides", []):
        for element in slide.get("pageElements", []) or []:
            _collect_text_from_element(element, parts)
    return set(PLACEHOLDER_RE.findall("\n".join(parts)))


def read_placeholders(slides_service, presentation_id: str) -> set[str]:
    presentation = _execute_with_retry(
        slides_service.presentations().get(presentationId=presentation_id)
    )
    return extract_placeholders_from_presentation(presentation)


def audit_placeholders(
    template_placeholders: set[str],
    available_replacements: set[str],
) -> dict[str, list[str]]:
    missing_values = sorted(template_placeholders - available_replacements)
    unused_values = sorted(available_replacements - template_placeholders)
    return {
        "template_placeholders": sorted(template_placeholders),
        "missing_values": missing_values,
        "unused_values": unused_values,
    }


def find_sheets_chart_object_ids(presentation: dict[str, Any]) -> list[str]:
    object_ids: list[str] = []
    for slide in presentation.get("slides", []):
        for element in slide.get("pageElements", []) or []:
            if "sheetsChart" in element and element.get("objectId"):
                object_ids.append(element["objectId"])
    return object_ids


def refresh_linked_sheets_charts(slides_service, presentation_id: str) -> int:
    presentation = _execute_with_retry(
        slides_service.presentations().get(presentationId=presentation_id)
    )
    chart_ids = find_sheets_chart_object_ids(presentation)
    if not chart_ids:
        return 0
    requests = [{"refreshSheetsChart": {"objectId": object_id}} for object_id in chart_ids]
    _execute_with_retry(
        slides_service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={"requests": requests},
        )
    )
    return len(chart_ids)


def _text_from_element(element: dict[str, Any]) -> str:
    parts: list[str] = []
    _collect_text_from_element(element, parts)
    return "".join(parts)


def _find_placeholder_shapes(presentation: dict[str, Any], placeholder: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for slide in presentation.get("slides", []):
        page_id = slide.get("objectId")
        for element in slide.get("pageElements", []) or []:
            if placeholder in _text_from_element(element):
                matches.append({"slide_id": page_id, "element": element})
    return matches


def _truncate(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _fmt_money(value: Any) -> str:
    return f"${float(value or 0):,.0f}"


def _fmt_int(value: Any) -> str:
    return f"{int(float(value or 0)):,}"


def _fmt_pct(value: Any) -> str:
    return f"{float(value or 0):.1f}%"


def _fmt_roas(value: Any) -> str:
    return f"{float(value or 0):.2f}"


def build_meta_top_ads_table_rows(kpis: dict) -> list[list[str]]:
    rows = [["Ad Name", "Ad Spend", "Ad Revenue", "% of Ad Revenue", "Sales", "Clicks", "ROAS", "CPS", "CR", "Leads", "CTR"]]
    for ad in kpis.get("meta_top_ads_detailed", [])[:10]:
        rows.append(
            [
                _truncate(ad.get("source"), 34),
                _fmt_money(ad.get("cost")),
                _fmt_money(ad.get("revenue")),
                _fmt_pct(ad.get("revenue_pct")),
                _fmt_int(ad.get("sales")),
                _fmt_int(ad.get("clicks")),
                _fmt_roas(ad.get("roas")),
                _fmt_money(ad.get("cps")),
                _fmt_pct(ad.get("cvr_pct")),
                _fmt_int(ad.get("leads")),
                _fmt_pct(ad.get("ctr_pct")),
            ]
        )
    while len(rows) < 11:
        rows.append(["N/A"] + [""] * 10)
    return rows


def build_funnel_stage_table_rows(kpis: dict, stage: str) -> list[list[str]]:
    rows = [["Rank", "Channel", "Ad Name", "Revenue", "ROAS", "Sales", "CPS"]]
    for index, ad in enumerate(kpis.get("top_ads_by_funnel_stage", {}).get(stage, [])[:3], start=1):
        rows.append(
            [
                str(index),
                _truncate(ad.get("traffic_source"), 8),
                _truncate(ad.get("source"), 26),
                _fmt_money(ad.get("revenue")),
                _fmt_roas(ad.get("roas")),
                _fmt_int(ad.get("sales")),
                _fmt_money(ad.get("cps")),
            ]
        )
    while len(rows) < 4:
        rows.append([str(len(rows)), "N/A", "N/A", "", "", "", ""])
    return rows


def _insert_table_text_requests(
    table_id: str,
    rows: list[list[str]],
    header_font_size: float = 5.4,
    body_font_size: float = 5.2,
) -> list[dict]:
    requests: list[dict] = []
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            requests.append(
                {
                    "insertText": {
                        "objectId": table_id,
                        "cellLocation": {"rowIndex": row_index, "columnIndex": column_index},
                        "insertionIndex": 0,
                        "text": value if value else " ",
                    }
                }
            )
            requests.append(
                {
                    "updateTextStyle": {
                        "objectId": table_id,
                        "cellLocation": {"rowIndex": row_index, "columnIndex": column_index},
                        "style": {
                            "fontFamily": "Outfit",
                            "fontSize": {
                                "magnitude": header_font_size if row_index == 0 else body_font_size,
                                "unit": "PT",
                            },
                            "bold": row_index == 0,
                            "foregroundColor": {"opaqueColor": {"rgbColor": {"red": 0, "green": 0, "blue": 0}}},
                        },
                        "fields": "fontFamily,fontSize,bold,foregroundColor",
                    }
                }
            )
    if rows:
        requests.append(
            {
                "updateTableCellProperties": {
                    "objectId": table_id,
                    "tableRange": {
                        "location": {"rowIndex": 0, "columnIndex": 0},
                        "rowSpan": len(rows),
                        "columnSpan": len(rows[0]),
                    },
                    "tableCellProperties": {
                        "tableCellBackgroundFill": {
                            "solidFill": {
                                "color": {"rgbColor": {"red": 1, "green": 1, "blue": 1}},
                                "alpha": 1,
                            }
                        }
                    },
                    "fields": "tableCellBackgroundFill.solidFill.color,tableCellBackgroundFill.solidFill.alpha",
                }
            }
        )
        requests.append(
            {
                "updateTableCellProperties": {
                    "objectId": table_id,
                    "tableRange": {
                        "location": {"rowIndex": 0, "columnIndex": 0},
                        "rowSpan": 1,
                        "columnSpan": len(rows[0]),
                    },
                    "tableCellProperties": {
                        "tableCellBackgroundFill": {
                            "solidFill": {
                                "color": {"rgbColor": {"red": 0.9, "green": 0.93, "blue": 1.0}},
                                "alpha": 1,
                            }
                        }
                    },
                    "fields": "tableCellBackgroundFill.solidFill.color,tableCellBackgroundFill.solidFill.alpha",
                }
            }
        )
    return requests


def _row_height_requests(table_id: str, row_heights: list[float]) -> list[dict]:
    return [
        {
            "updateTableRowProperties": {
                "objectId": table_id,
                "rowIndices": [index],
                "tableRowProperties": {
                    "minRowHeight": {"magnitude": height, "unit": "EMU"},
                },
                "fields": "minRowHeight",
            }
        }
        for index, height in enumerate(row_heights)
    ]


def _column_width_requests(table_id: str, widths: list[float]) -> list[dict]:
    return [
        {
            "updateTableColumnProperties": {
                "objectId": table_id,
                "columnIndices": [index],
                "tableColumnProperties": {"columnWidth": {"magnitude": width, "unit": "EMU"}},
                "fields": "columnWidth",
            }
        }
        for index, width in enumerate(widths)
    ]


def _base_transform(placeholder: dict[str, Any], x: float | None = None, y: float | None = None) -> dict:
    transform = dict(placeholder.get("transform", {}))
    transform["scaleX"] = 1
    transform["scaleY"] = 1
    transform.setdefault("unit", "EMU")
    if x is not None:
        transform["translateX"] = x
    if y is not None:
        transform["translateY"] = y
    return transform


def _element_width_height(element: dict[str, Any]) -> tuple[float, float]:
    size = element.get("size", {})
    transform = element.get("transform", {})
    scale_x = float(transform.get("scaleX", 1) or 1)
    scale_y = float(transform.get("scaleY", 1) or 1)
    width = float(size.get("width", {}).get("magnitude", 0)) * scale_x
    height = float(size.get("height", {}).get("magnitude", 0)) * scale_y
    return width, height


def _make_table_create_request(
    table_id: str,
    slide_id: str,
    rows: int,
    columns: int,
    width: float,
    height: float,
    transform: dict,
) -> dict:
    return {
        "createTable": {
            "objectId": table_id,
            "elementProperties": {
                "pageObjectId": slide_id,
                "size": {
                    "width": {"magnitude": width, "unit": "EMU"},
                    "height": {"magnitude": height, "unit": "EMU"},
                },
                "transform": transform,
            },
            "rows": rows,
            "columns": columns,
        }
    }


def _build_meta_table_requests(match: dict[str, Any], kpis: dict, index: int) -> list[dict]:
    element = match["element"]
    slide_id = match["slide_id"]
    width, height = _element_width_height(element)
    table_height = min(height, 3.25 * EMU_PER_INCH)
    table_id = f"metaTop10Table{index}"
    rows = build_meta_top_ads_table_rows(kpis)
    name_width = max(width * 0.28, 2.1 * EMU_PER_INCH)
    remaining_width = max(width - name_width, 1)
    column_widths = [name_width] + [remaining_width / 10] * 10
    requests = [
        {"deleteObject": {"objectId": element["objectId"]}},
        _make_table_create_request(table_id, slide_id, len(rows), len(rows[0]), width, table_height, _base_transform(element)),
    ]
    requests.extend(_column_width_requests(table_id, column_widths))
    requests.extend(_row_height_requests(table_id, [0.27 * EMU_PER_INCH] + [0.245 * EMU_PER_INCH] * 10))
    requests.extend(_insert_table_text_requests(table_id, rows, header_font_size=4.8, body_font_size=4.6))
    return requests


def _build_funnel_tables_requests(match: dict[str, Any], kpis: dict, index: int) -> list[dict]:
    element = match["element"]
    slide_id = match["slide_id"]
    width, height = _element_width_height(element)
    base_transform = _base_transform(element)
    x = float(base_transform.get("translateX", 0))
    y = float(base_transform.get("translateY", 0))
    table_width = min(max(width * 0.44, 4.0 * EMU_PER_INCH), 4.05 * EMU_PER_INCH)
    top_height = min(max(height * 0.55, 1.3 * EMU_PER_INCH), 1.65 * EMU_PER_INCH)
    bottom_height = min(max(height * 0.42, 1.05 * EMU_PER_INCH), 1.35 * EMU_PER_INCH)
    positions = {
        "TOF": (x, y, top_height),
        "MOF": (x + width - table_width, y, top_height),
        "BOF": (x + (width - table_width) / 2, y + 2.35 * EMU_PER_INCH, bottom_height),
    }
    requests: list[dict] = [{"deleteObject": {"objectId": element["objectId"]}}]
    for stage in ("TOF", "MOF", "BOF"):
        table_id = f"funnelTop3{stage}Table{index}"
        rows = build_funnel_stage_table_rows(kpis, stage)
        table_x, table_y, table_height = positions[stage]
        transform = _base_transform(element, x=table_x, y=table_y)
        requests.append(_make_table_create_request(table_id, slide_id, len(rows), len(rows[0]), table_width, table_height, transform))
        widths = [
            0.45 * EMU_PER_INCH,
            0.55 * EMU_PER_INCH,
            1.15 * EMU_PER_INCH,
            0.55 * EMU_PER_INCH,
            0.45 * EMU_PER_INCH,
            0.45 * EMU_PER_INCH,
            0.50 * EMU_PER_INCH,
        ]
        requests.extend(_column_width_requests(table_id, widths))
        requests.extend(_row_height_requests(table_id, [0.31 * EMU_PER_INCH] + [0.30 * EMU_PER_INCH] * 3))
        requests.extend(_insert_table_text_requests(table_id, rows, header_font_size=5.0, body_font_size=4.8))
    return requests


def insert_creative_metric_tables(slides_service, presentation_id: str, kpis: dict, batch_size: int = 100) -> int:
    """Replace creative metric table placeholders with native editable Slides tables."""
    presentation = _execute_with_retry(slides_service.presentations().get(presentationId=presentation_id))
    requests: list[dict] = []
    for index, match in enumerate(_find_placeholder_shapes(presentation, "{{META_TOP_10_ADS_TABLE}}"), start=1):
        requests.extend(_build_meta_table_requests(match, kpis, index))
    for index, match in enumerate(_find_placeholder_shapes(presentation, "{{TOP_3_FUNNEL_ADS_TABLE}}"), start=1):
        requests.extend(_build_funnel_tables_requests(match, kpis, index))
    for start in range(0, len(requests), batch_size):
        chunk = requests[start : start + batch_size]
        _execute_with_retry(
            slides_service.presentations().batchUpdate(
                presentationId=presentation_id,
                body={"requests": chunk},
            )
        )
    return len(requests)


def export_presentation(
    drive_service,
    presentation_id: str,
    output_path: str | Path,
    mime_type: str,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = _execute_with_retry(
        drive_service.files().export(fileId=presentation_id, mimeType=mime_type)
    )
    output_path.write_bytes(data)
    return output_path


def get_slide_thumbnail_urls(slides_service, presentation_id: str, max_slides: int | None = None) -> list[str]:
    presentation = slides_service.presentations().get(presentationId=presentation_id).execute()
    urls: list[str] = []
    for slide in presentation.get("slides", [])[:max_slides]:
        page_id = slide.get("objectId")
        if not page_id:
            continue
        thumbnail = (
            slides_service.presentations()
            .pages()
            .getThumbnail(
                presentationId=presentation_id,
                pageObjectId=page_id,
                thumbnailProperties_mimeType="PNG",
                thumbnailProperties_thumbnailSize="MEDIUM",
            )
        )
        thumbnail = _execute_with_retry(thumbnail)
        if thumbnail.get("contentUrl"):
            urls.append(thumbnail["contentUrl"])
    return urls
