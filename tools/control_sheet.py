"""Master control sheet parsing and centralized batch-run logging."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from tools.google_sheet_report_data import ensure_sheet_exists, quote_sheet_name, read_sheet_values, values_to_dataframe
from tools.google_workspace import extract_file_id

REQUIRED_CLIENT_COLUMNS = {
    "active",
    "client_name",
    "client_key",
    "spreadsheet_url_or_id",
    "template_presentation_url_or_id",
    "output_folder_id",
}
DEFAULT_CLIENTS_SHEET = "Clients"
DEFAULT_RUNS_SHEET = "Runs"
CURRENCY_CLIENT_COLUMNS = ("source_currency", "report_currency", "fx_policy")


@dataclass(frozen=True)
class ControlSheetClient:
    active: bool
    client_name: str
    client_key: str
    spreadsheet_id: str
    template_presentation_id: str
    output_folder_id: str
    campaigns_tab: str = "Campaigns"
    ads_tab: str = "Ads"
    timezone: str = ""
    insights_provider: str = "auto"
    source_currency: str = "USD"
    report_currency: str = "USD"
    fx_policy: str = "none"


def _normalize_column(value: str) -> str:
    return str(value).strip().lower().replace(" ", "_").replace("-", "_")


def _parse_active(value: Any) -> bool:
    normalized = str(value).strip().lower()
    return normalized in {"1", "true", "yes", "y", "active"}


def _column_a1(index: int) -> str:
    letters = ""
    value = index
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def ensure_control_sheet_currency_columns(
    sheets_service,
    spreadsheet_id: str,
    sheet_name: str = DEFAULT_CLIENTS_SHEET,
) -> list[str]:
    """Append optional currency settings without altering existing client columns."""
    headers = read_sheet_values(sheets_service, spreadsheet_id, sheet_name, "A1:Z1")
    if not headers:
        raise ValueError(f"Control sheet {sheet_name!r} has no header row.")
    existing = {_normalize_column(value) for value in headers[0]}
    missing = [column for column in CURRENCY_CLIENT_COLUMNS if column not in existing]
    if not missing:
        return []
    start = _column_a1(len(headers[0]) + 1)
    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{quote_sheet_name(sheet_name)}!{start}1",
        valueInputOption="USER_ENTERED",
        body={"values": [missing]},
    ).execute()
    return missing


def _ensure_run_headers(sheets_service, spreadsheet_id: str, sheet_name: str, headers: list[str]) -> None:
    ensure_sheet_exists(sheets_service, spreadsheet_id, sheet_name)
    existing = read_sheet_values(sheets_service, spreadsheet_id, sheet_name, "A1:Z1")
    if existing:
        return
    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{quote_sheet_name(sheet_name)}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [headers]},
    ).execute()


def load_control_sheet_clients(
    sheets_service,
    spreadsheet_id: str,
    sheet_name: str = DEFAULT_CLIENTS_SHEET,
    active_only: bool = True,
) -> list[ControlSheetClient]:
    df = values_to_dataframe(read_sheet_values(sheets_service, spreadsheet_id, sheet_name))
    if df.empty:
        return []

    normalized = {_normalize_column(column): column for column in df.columns}
    missing = sorted(REQUIRED_CLIENT_COLUMNS - set(normalized))
    if missing:
        raise ValueError(f"Control sheet is missing required client columns: {missing}")

    clients: list[ControlSheetClient] = []
    for _, row in df.iterrows():
        is_active = _parse_active(row[normalized["active"]])
        if active_only and not is_active:
            continue

        campaigns_tab = str(row.get(normalized.get("campaigns_tab", ""), "")).strip() or "Campaigns"
        ads_tab = str(row.get(normalized.get("ads_tab", ""), "")).strip() or "Ads"
        timezone_value = str(row.get(normalized.get("timezone", ""), "")).strip()
        insights_provider = (
            str(row.get(normalized.get("insights_provider", ""), "")).strip().lower() or "auto"
        )
        source_currency = str(row.get(normalized.get("source_currency", ""), "")).strip().upper() or "USD"
        report_currency = str(row.get(normalized.get("report_currency", ""), "")).strip().upper() or "USD"
        fx_policy = str(row.get(normalized.get("fx_policy", ""), "")).strip().lower() or "none"

        client = ControlSheetClient(
            active=is_active,
            client_name=str(row[normalized["client_name"]]).strip(),
            client_key=str(row[normalized["client_key"]]).strip(),
            spreadsheet_id=extract_file_id(str(row[normalized["spreadsheet_url_or_id"]]).strip()),
            template_presentation_id=extract_file_id(
                str(row[normalized["template_presentation_url_or_id"]]).strip()
            ),
            output_folder_id=extract_file_id(str(row[normalized["output_folder_id"]]).strip()),
            campaigns_tab=campaigns_tab,
            ads_tab=ads_tab,
            timezone=timezone_value,
            insights_provider=insights_provider,
            source_currency=source_currency,
            report_currency=report_currency,
            fx_policy=fx_policy,
        )
        if not client.client_key:
            raise ValueError(f"Client row for {client.client_name!r} is missing client_key.")
        if not client.spreadsheet_id or not client.template_presentation_id or not client.output_folder_id:
            raise ValueError(
                f"Client row for {client.client_name!r} is missing spreadsheet/template/output folder configuration."
            )
        clients.append(client)
    return clients


def select_control_sheet_clients(
    clients: list[ControlSheetClient],
    run_mode: str,
    client_key: str = "",
) -> list[ControlSheetClient]:
    if run_mode == "all":
        return clients
    if run_mode != "one":
        raise ValueError(f"Unsupported run mode: {run_mode}")
    wanted = client_key.strip().lower()
    matched = [client for client in clients if client.client_key.lower() == wanted]
    if not matched:
        raise ValueError(f"Client key {client_key!r} was not found in the control sheet.")
    return matched


def make_control_run_log_row(
    *,
    batch_run_id: str,
    run_mode: str,
    client: ControlSheetClient,
    month: str,
    year: int,
    status: str,
    requested_insights_provider: str,
    used_insights_provider: str,
    presentation_url: str = "",
    error_summary: str = "",
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "batch_run_id": batch_run_id,
        "run_mode": run_mode,
        "client_key": client.client_key,
        "client_name": client.client_name,
        "period": f"{month} {year}",
        "status": status,
        "spreadsheet_id": client.spreadsheet_id,
        "presentation_url": presentation_url,
        "requested_insights_provider": requested_insights_provider,
        "used_insights_provider": used_insights_provider,
        "error_summary": error_summary,
        "validation_json": json.dumps(validation or {}, default=str),
    }
    return row


def append_control_run_log(
    sheets_service,
    spreadsheet_id: str,
    row: dict[str, Any],
    sheet_name: str = DEFAULT_RUNS_SHEET,
) -> None:
    headers = [
        "timestamp_utc",
        "batch_run_id",
        "run_mode",
        "client_key",
        "client_name",
        "period",
        "status",
        "spreadsheet_id",
        "presentation_url",
        "requested_insights_provider",
        "used_insights_provider",
        "error_summary",
        "validation_json",
    ]
    _ensure_run_headers(sheets_service, spreadsheet_id, sheet_name, headers)
    values = [[row.get(header, "") for header in headers]]
    sheets_service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{quote_sheet_name(sheet_name)}!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": values},
    ).execute()


def client_to_dict(client: ControlSheetClient) -> dict[str, Any]:
    return asdict(client)
