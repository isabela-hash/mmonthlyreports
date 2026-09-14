"""Operational helpers for the MT report portal."""
from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from tools.control_sheet import (
    DEFAULT_CLIENTS_SHEET,
    DEFAULT_RUNS_SHEET,
    ensure_control_sheet_currency_columns,
    load_control_sheet_clients,
)
from tools.google_sheet_report_data import load_report_sheet, quote_sheet_name, read_sheet_values
from tools.google_workspace import build_workspace_services, extract_file_id
from tools.report_periods import resolve_reporting_window
from tools.run_google_slides_report import build_run_namespace, run_report
from tools.validate_data import validate_or_raise

FOLDER_MIME = "application/vnd.google-apps.folder"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
PRESENTATION_MIME = "application/vnd.google-apps.presentation"

REPORT_DATA_HEADERS = [
    "Source",
    "Traffic Source",
    "Source Link",
    "Click",
    "Cost",
    "Revenue",
    "Recurring Revenue",
    "Sales",
    "Leads",
    "Total Revenue",
    "Impressions",
    "Average Order Value",
    "Client",
    "Month",
    "Year",
    "Funnel",
]


def slugify_client_key(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise ValueError("Client key cannot be blank.")
    return slug


def _normalize_column(value: str) -> str:
    return str(value).strip().lower().replace(" ", "_").replace("-", "_")


def _parse_active(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "active", "on"}


def _escape_drive_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _find_file(drive_service, name: str, parent_id: str, mime_type: str) -> dict | None:
    query = (
        f"name = '{_escape_drive_query(name)}' "
        f"and mimeType = '{mime_type}' "
        f"and '{_escape_drive_query(parent_id)}' in parents "
        "and trashed = false"
    )
    result = (
        drive_service.files()
        .list(q=query, fields="files(id,name,mimeType,webViewLink,parents)", pageSize=10)
        .execute()
    )
    files = result.get("files", [])
    return files[0] if files else None


def _first_available_defaults(drive_service, clients: list) -> tuple[str, str]:
    if not clients:
        raise ValueError("Template and parent folder are required when the control sheet has no clients.")
    template_id = clients[0].template_presentation_id
    folder_meta = drive_service.files().get(fileId=clients[0].output_folder_id, fields="parents").execute()
    parents = folder_meta.get("parents", [])
    if not parents:
        raise ValueError("Could not infer the parent reports folder from existing client folders.")
    return template_id, parents[0]


def _ensure_campaign_ads_headers(sheets_service, spreadsheet_id: str) -> None:
    for tab_name in ["Campaigns", "Ads"]:
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{quote_sheet_name(tab_name)}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [REPORT_DATA_HEADERS]},
        ).execute()


def _create_data_spreadsheet(sheets_service, drive_service, name: str, folder_id: str) -> dict:
    created = sheets_service.spreadsheets().create(
        body={
            "properties": {"title": name},
            "sheets": [
                {
                    "properties": {
                        "title": "Campaigns",
                        "gridProperties": {"rowCount": 1000, "columnCount": len(REPORT_DATA_HEADERS)},
                    }
                },
                {
                    "properties": {
                        "title": "Ads",
                        "gridProperties": {"rowCount": 1000, "columnCount": len(REPORT_DATA_HEADERS)},
                    }
                },
                {"properties": {"title": "KPI Output"}},
                {"properties": {"title": "Run Log"}},
            ],
        },
        fields="spreadsheetId,spreadsheetUrl",
    ).execute()
    spreadsheet_id = created["spreadsheetId"]
    meta = drive_service.files().get(fileId=spreadsheet_id, fields="parents").execute()
    parents = ",".join(meta.get("parents", []))
    drive_service.files().update(
        fileId=spreadsheet_id,
        addParents=folder_id,
        removeParents=parents,
        fields="id,name,mimeType,webViewLink,parents",
    ).execute()
    _ensure_campaign_ads_headers(sheets_service, spreadsheet_id)
    return drive_service.files().get(
        fileId=spreadsheet_id,
        fields="id,name,mimeType,webViewLink,parents",
    ).execute()


def latest_successful_run_urls(
    sheets_service,
    control_sheet_id: str,
    runs_sheet: str,
    month: str,
    year: int,
) -> dict[str, str]:
    values = read_sheet_values(sheets_service, control_sheet_id, runs_sheet, "A1:M")
    if not values:
        return {}
    headers = [str(header).strip() for header in values[0]]
    wanted_period = f"{month} {year}"
    latest: dict[str, str] = {}
    for row in values[1:]:
        padded = row + [""] * max(0, len(headers) - len(row))
        item = dict(zip(headers, padded))
        key = str(item.get("client_key", "")).strip()
        if (
            key
            and str(item.get("period", "")).strip() == wanted_period
            and str(item.get("status", "")).strip().lower() == "ok"
            and str(item.get("presentation_url", "")).strip()
        ):
            latest[key] = str(item["presentation_url"]).strip()
    return latest


def drive_has_period_deck(drive_service, client, month: str, year: int) -> bool:
    query = (
        f"'{_escape_drive_query(client.output_folder_id)}' in parents "
        f"and mimeType = '{PRESENTATION_MIME}' "
        "and trashed = false "
        f"and name contains '{_escape_drive_query(f'{month} {year}')}'"
    )
    result = drive_service.files().list(q=query, fields="files(id)", pageSize=1).execute()
    return bool(result.get("files", []))


class ReportOps:
    def __init__(
        self,
        services: dict | None = None,
        control_sheet_id: str = "",
        clients_sheet: str = DEFAULT_CLIENTS_SHEET,
        runs_sheet: str = DEFAULT_RUNS_SHEET,
    ):
        self.services = services or build_workspace_services()
        self.control_sheet_id = extract_file_id(control_sheet_id)
        self.clients_sheet = clients_sheet
        self.runs_sheet = runs_sheet

    def load_clients(self, active_only: bool = False) -> list:
        return load_control_sheet_clients(
            self.services["sheets"],
            self.control_sheet_id,
            sheet_name=self.clients_sheet,
            active_only=active_only,
        )

    def list_clients(self, month: str = "", year: int | None = None) -> list[dict[str, Any]]:
        clients = self.load_clients(active_only=False)
        latest = latest_successful_run_urls(
            self.services["sheets"],
            self.control_sheet_id,
            self.runs_sheet,
            month,
            int(year),
        ) if month and year else {}
        rows = []
        for client in clients:
            item = asdict(client)
            item["latest_report_url"] = latest.get(client.client_key, "")
            rows.append(item)
        return rows

    def create_client(
        self,
        client_name: str,
        client_key: str = "",
        template_presentation_url_or_id: str = "",
        parent_folder_id: str = "",
        active: bool = False,
        timezone: str = "America/New_York",
        insights_provider: str = "auto",
        source_currency: str = "USD",
        report_currency: str = "USD",
        fx_policy: str = "none",
    ) -> dict[str, Any]:
        client_name = client_name.strip()
        if not client_name:
            raise ValueError("client_name is required.")
        client_key = slugify_client_key(client_key or client_name)
        existing = {client.client_key.lower() for client in self.load_clients(active_only=False)}
        if client_key.lower() in existing:
            raise ValueError(f"Client key {client_key!r} already exists.")

        clients = self.load_clients(active_only=False)
        if not template_presentation_url_or_id or not parent_folder_id:
            default_template_id, default_parent_id = _first_available_defaults(self.services["drive"], clients)
            template_presentation_url_or_id = template_presentation_url_or_id or default_template_id
            parent_folder_id = parent_folder_id or default_parent_id

        template_id = extract_file_id(template_presentation_url_or_id)
        parent_folder_id = extract_file_id(parent_folder_id)
        folder_name = f"{client_name} Monthly Reports"
        sheet_name = f"{client_name} Monthly Data - 2026"
        folder = _find_file(self.services["drive"], folder_name, parent_folder_id, FOLDER_MIME)
        folder_created = False
        if not folder:
            folder = self.services["drive"].files().create(
                body={"name": folder_name, "mimeType": FOLDER_MIME, "parents": [parent_folder_id]},
                fields="id,name,mimeType,webViewLink,parents",
            ).execute()
            folder_created = True

        spreadsheet = _find_file(self.services["drive"], sheet_name, folder["id"], SHEET_MIME)
        spreadsheet_created = False
        if not spreadsheet:
            spreadsheet = _create_data_spreadsheet(
                self.services["sheets"],
                self.services["drive"],
                sheet_name,
                folder["id"],
            )
            spreadsheet_created = True

        ensure_control_sheet_currency_columns(
            self.services["sheets"], self.control_sheet_id, self.clients_sheet
        )
        row = [
            "yes" if active else "no",
            client_name,
            client_key,
            spreadsheet["webViewLink"],
            f"https://docs.google.com/presentation/d/{template_id}/edit?usp=drive_link",
            folder["webViewLink"],
            "Campaigns",
            "Ads",
            timezone,
            insights_provider,
            source_currency.strip().upper() or "USD",
            report_currency.strip().upper() or "USD",
            fx_policy.strip().lower() or "none",
        ]
        self.services["sheets"].spreadsheets().values().append(
            spreadsheetId=self.control_sheet_id,
            range=f"{quote_sheet_name(self.clients_sheet)}!A1",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
        return {
            "client_name": client_name,
            "client_key": client_key,
            "active": active,
            "folder_created": folder_created,
            "folder_url": folder["webViewLink"],
            "spreadsheet_created": spreadsheet_created,
            "spreadsheet_url": spreadsheet["webViewLink"],
            "template_presentation_id": template_id,
        }

    def set_client_active(self, client_key: str, active: bool) -> dict[str, Any]:
        values = read_sheet_values(self.services["sheets"], self.control_sheet_id, self.clients_sheet, "A1:J")
        if not values:
            raise ValueError("Control sheet Clients tab is empty.")
        headers = [_normalize_column(header) for header in values[0]]
        try:
            active_col = headers.index("active")
            key_col = headers.index("client_key")
        except ValueError as exc:
            raise ValueError("Clients tab must include active and client_key columns.") from exc
        wanted = client_key.strip().lower()
        for index, row in enumerate(values[1:], start=2):
            if len(row) > key_col and str(row[key_col]).strip().lower() == wanted:
                column_letter = chr(ord("A") + active_col)
                value = "yes" if active else "no"
                self.services["sheets"].spreadsheets().values().update(
                    spreadsheetId=self.control_sheet_id,
                    range=f"{quote_sheet_name(self.clients_sheet)}!{column_letter}{index}",
                    valueInputOption="USER_ENTERED",
                    body={"values": [[value]]},
                ).execute()
                return {"client_key": client_key, "active": active}
        raise ValueError(f"Client key {client_key!r} was not found in the control sheet.")

    def preflight_report(
        self,
        client_key: str,
        month: str,
        year: int,
        allow_first_month_baseline: bool = False,
        include_inactive: bool = True,
    ) -> dict[str, Any]:
        window = resolve_reporting_window(month, int(year))
        clients = self.load_clients(active_only=not include_inactive)
        matches = [client for client in clients if client.client_key.lower() == client_key.strip().lower()]
        if not matches:
            raise ValueError(f"Client key {client_key!r} was not found in the control sheet.")
        client = matches[0]

        current_campaigns = load_report_sheet(
            self.services["sheets"], client.spreadsheet_id, client.campaigns_tab, client.client_name, window.month, window.year
        )
        current_ads = load_report_sheet(
            self.services["sheets"], client.spreadsheet_id, client.ads_tab, client.client_name, window.month, window.year
        )
        prev_campaigns = load_report_sheet(
            self.services["sheets"], client.spreadsheet_id, client.campaigns_tab, client.client_name, window.prev_month, window.prev_year
        )
        prev_ads = load_report_sheet(
            self.services["sheets"], client.spreadsheet_id, client.ads_tab, client.client_name, window.prev_month, window.prev_year
        )

        errors = []
        if current_campaigns.empty:
            errors.append("Current-month Campaigns rows are missing.")
        if current_ads.empty:
            errors.append("Current-month Ads rows are missing.")
        checkpoints = {}
        if not current_campaigns.empty:
            try:
                checkpoints = validate_or_raise(current_campaigns)
            except Exception as exc:
                errors.append(str(exc))
        previous_missing = prev_campaigns.empty and prev_ads.empty
        if (prev_campaigns.empty or prev_ads.empty) and not (allow_first_month_baseline and previous_missing):
            errors.append("Previous-month data is missing. Enable first-month baseline to proceed.")

        audit = run_report(
            build_run_namespace(
                template_presentation=client.template_presentation_id,
                client=client.client_name,
                month=window.month,
                year=window.year,
                prev_month=window.prev_month,
                prev_year=window.prev_year,
                next_month=window.next_month,
                next_year=window.next_year,
                audit_only=True,
            ),
            services=self.services,
        )
        if audit["audit"]["missing_values"]:
            errors.append("Template audit has missing values.")

        latest = latest_successful_run_urls(
            self.services["sheets"],
            self.control_sheet_id,
            self.runs_sheet,
            window.month,
            window.year,
        )
        return {
            "client_key": client.client_key,
            "client_name": client.client_name,
            "period": f"{window.month} {window.year}",
            "prev_period": f"{window.prev_month} {window.prev_year}",
            "current_campaign_rows": len(current_campaigns),
            "current_ad_rows": len(current_ads),
            "previous_campaign_rows": len(prev_campaigns),
            "previous_ad_rows": len(prev_ads),
            "previous_missing": previous_missing,
            "first_month_baseline": bool(allow_first_month_baseline and previous_missing),
            "latest_report_url": latest.get(client.client_key, ""),
            "audit": audit["audit"],
            "checkpoints": checkpoints,
            "status": "ok" if not errors else "blocked",
            "errors": errors,
        }
