#!/usr/bin/env python3
"""Run one or many client reports from a master control sheet."""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.control_sheet import (
    DEFAULT_CLIENTS_SHEET,
    DEFAULT_RUNS_SHEET,
    append_control_run_log,
    load_control_sheet_clients,
    make_control_run_log_row,
    select_control_sheet_clients,
)
from tools.google_workspace import build_workspace_services, extract_file_id
from tools.google_sheet_report_data import read_sheet_values
from tools.report_periods import resolve_reporting_window
from tools.run_google_slides_report import build_run_namespace, ensure_supported_python_version, run_report


PRESENTATION_MIME = "application/vnd.google-apps.presentation"


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run monthly reports for one or many clients from a control sheet.")
    parser.add_argument(
        "--control-sheet",
        default=os.environ.get("MASTER_CONTROL_SHEET_ID", os.environ.get("CONTROL_SHEET_ID", "")),
        help="Master control Google Sheet URL or ID.",
    )
    parser.add_argument("--clients-sheet", default=os.environ.get("CONTROL_SHEET_CLIENTS_SHEET", DEFAULT_CLIENTS_SHEET))
    parser.add_argument("--runs-sheet", default=os.environ.get("CONTROL_SHEET_RUNS_SHEET", DEFAULT_RUNS_SHEET))
    parser.add_argument("--run-mode", choices=["all", "one", "missing"], default=os.environ.get("RUN_MODE", "all"))
    parser.add_argument("--client-key", default=os.environ.get("CLIENT_KEY", ""))
    parser.add_argument("--month", default=os.environ.get("REPORT_MONTH", ""))
    parser.add_argument("--year", type=int, default=int(os.environ["REPORT_YEAR"]) if os.environ.get("REPORT_YEAR") else None)
    parser.add_argument("--prev-month", default=os.environ.get("REPORT_PREV_MONTH", ""))
    parser.add_argument(
        "--prev-year",
        type=int,
        default=int(os.environ["REPORT_PREV_YEAR"]) if os.environ.get("REPORT_PREV_YEAR") else None,
    )
    parser.add_argument("--next-month", default=os.environ.get("REPORT_NEXT_MONTH", ""))
    parser.add_argument(
        "--next-year",
        type=int,
        default=int(os.environ["REPORT_NEXT_YEAR"]) if os.environ.get("REPORT_NEXT_YEAR") else None,
    )
    parser.add_argument(
        "--insights-provider",
        default=os.environ.get("INSIGHTS_PROVIDER", ""),
        help="Optional override for all clients. Leave blank to use each client's configured provider.",
    )
    parser.add_argument("--fail-fast", action="store_true", default=os.environ.get("FAIL_FAST", "").lower() == "true")
    parser.add_argument("--write-client-run-log", action="store_true")
    parser.add_argument("--write-client-kpi-output", action="store_true")
    parser.add_argument(
        "--allow-first-month-baseline",
        action="store_true",
        default=_env_flag("ALLOW_FIRST_MONTH_BASELINE"),
    )
    parser.add_argument("--include-inactive", action="store_true", default=_env_flag("INCLUDE_INACTIVE"))
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if not args.control_sheet:
        raise ValueError("--control-sheet is required or MASTER_CONTROL_SHEET_ID/CONTROL_SHEET_ID must be set.")
    if args.run_mode == "one" and not args.client_key:
        raise ValueError("--client-key is required when --run-mode one is used.")


def _escape_drive_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _successful_run_keys(
    sheets_service,
    control_sheet_id: str,
    runs_sheet: str,
    month: str,
    year: int,
) -> set[str]:
    values = read_sheet_values(sheets_service, control_sheet_id, runs_sheet, "A1:M")
    if not values:
        return set()
    headers = [str(header).strip() for header in values[0]]
    successful: set[str] = set()
    wanted_period = f"{month} {year}"
    for row in values[1:]:
        padded = row + [""] * max(0, len(headers) - len(row))
        item = dict(zip(headers, padded))
        if (
            str(item.get("period", "")).strip() == wanted_period
            and str(item.get("status", "")).strip().lower() == "ok"
            and str(item.get("presentation_url", "")).strip()
        ):
            successful.add(str(item.get("client_key", "")).strip().lower())
    return successful


def _drive_has_period_deck(drive_service, client, month: str, year: int) -> bool:
    query = (
        f"'{_escape_drive_query(client.output_folder_id)}' in parents "
        f"and mimeType = '{PRESENTATION_MIME}' "
        f"and trashed = false "
        f"and name contains '{_escape_drive_query(f'{month} {year}')}'"
    )
    result = (
        drive_service.files()
        .list(q=query, fields="files(id)", pageSize=1)
        .execute()
    )
    return bool(result.get("files", []))


def select_missing_report_clients(
    services: dict,
    control_sheet_id: str,
    runs_sheet: str,
    clients: list,
    month: str,
    year: int,
) -> list:
    successful_keys = _successful_run_keys(services["sheets"], control_sheet_id, runs_sheet, month, year)
    missing = []
    for client in clients:
        key = client.client_key.strip().lower()
        if key in successful_keys:
            continue
        if _drive_has_period_deck(services["drive"], client, month, year):
            continue
        missing.append(client)
    return missing


def main() -> int:
    args = parse_args()
    ensure_supported_python_version()
    validate_args(args)

    window = resolve_reporting_window(
        args.month or None,
        args.year,
        prev_month=args.prev_month or None,
        prev_year=args.prev_year,
        next_month=args.next_month or None,
        next_year=args.next_year,
    )
    services = build_workspace_services()
    control_sheet_id = extract_file_id(args.control_sheet)
    clients = load_control_sheet_clients(
        services["sheets"],
        control_sheet_id,
        sheet_name=args.clients_sheet,
        active_only=not args.include_inactive,
    )
    if args.run_mode == "missing":
        selected_clients = select_missing_report_clients(
            services,
            control_sheet_id,
            args.runs_sheet,
            clients,
            window.month,
            window.year,
        )
    else:
        selected_clients = select_control_sheet_clients(clients, args.run_mode, client_key=args.client_key)
    batch_run_id = str(uuid.uuid4())

    summaries: list[dict] = []
    failures: list[dict] = []
    for client in selected_clients:
        requested_provider = (args.insights_provider or client.insights_provider or "auto").strip().lower()
        client_args = build_run_namespace(
            spreadsheet=client.spreadsheet_id,
            template_presentation=client.template_presentation_id,
            client=client.client_name,
            month=window.month,
            year=window.year,
            prev_month=window.prev_month,
            prev_year=window.prev_year,
            next_month=window.next_month,
            next_year=window.next_year,
            campaigns_sheet=client.campaigns_tab,
            ads_sheet=client.ads_tab,
            output_folder_id=client.output_folder_id,
            source_currency=getattr(client, "source_currency", "USD"),
            report_currency=getattr(client, "report_currency", "USD"),
            fx_policy=getattr(client, "fx_policy", "none"),
            insights_provider=requested_provider,
            skip_run_log=not args.write_client_run_log,
            skip_kpi_output=not args.write_client_kpi_output,
            allow_first_month_baseline=args.allow_first_month_baseline,
        )
        try:
            summary = run_report(client_args, services=services)
            append_control_run_log(
                services["sheets"],
                control_sheet_id,
                make_control_run_log_row(
                    batch_run_id=batch_run_id,
                    run_mode=args.run_mode,
                    client=client,
                    month=window.month,
                    year=window.year,
                    status=summary["status"],
                    requested_insights_provider=requested_provider,
                    used_insights_provider=summary["used_insights_provider"],
                    presentation_url=summary.get("presentation", {}).get("webViewLink", ""),
                    validation={
                        "remaining_placeholders": summary.get("remaining_placeholders", []),
                        "prev_period": summary.get("prev_period", ""),
                        "first_month_baseline": summary.get("first_month_baseline", False),
                        "fx": summary.get("fx", {}),
                    },
                ),
                sheet_name=args.runs_sheet,
            )
            summaries.append(summary)
        except Exception as exc:
            failure = {
                "client_key": client.client_key,
                "client_name": client.client_name,
                "error": str(exc),
            }
            append_control_run_log(
                services["sheets"],
                control_sheet_id,
                make_control_run_log_row(
                    batch_run_id=batch_run_id,
                    run_mode=args.run_mode,
                    client=client,
                    month=window.month,
                    year=window.year,
                    status="error",
                    requested_insights_provider=requested_provider,
                    used_insights_provider="none",
                    error_summary=str(exc),
                ),
                sheet_name=args.runs_sheet,
            )
            failures.append(failure)
            if args.fail_fast:
                break

    payload = {
        "batch_run_id": batch_run_id,
        "run_mode": args.run_mode,
        "period": f"{window.month} {window.year}",
        "selected_clients": [client.client_key for client in selected_clients],
        "success_count": len(summaries),
        "failure_count": len(failures),
        "failures": failures,
        "summaries": summaries,
    }
    print(json.dumps(payload, indent=2, default=str))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
