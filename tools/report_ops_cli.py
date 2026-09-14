#!/usr/bin/env python3
"""JSON CLI adapter for the MT Ops Portal.

The Vercel web app calls this script from server-side API routes. Keeping the
Google Workspace/report logic here lets the portal reuse the existing Python
pipeline instead of duplicating report behavior in TypeScript.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.report_ops import ReportOps, latest_successful_run_urls
from tools.report_periods import resolve_reporting_window
from tools.alpha_geo_report import load_alpha_geo_snapshot


def _parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.payload:
        return json.loads(args.payload)
    raw = sys.stdin.read().strip()
    return json.loads(raw) if raw else {}


def _ops() -> ReportOps:
    control_sheet = os.environ.get("MASTER_CONTROL_SHEET_ID", os.environ.get("CONTROL_SHEET_ID", "")).strip()
    if not control_sheet:
        raise EnvironmentError("MASTER_CONTROL_SHEET_ID or CONTROL_SHEET_ID must be set.")
    return ReportOps(
        control_sheet_id=control_sheet,
        clients_sheet=os.environ.get("CONTROL_SHEET_CLIENTS_SHEET", "Clients"),
        runs_sheet=os.environ.get("CONTROL_SHEET_RUNS_SHEET", "Runs"),
    )


def _dashboard(payload: dict[str, Any]) -> dict[str, Any]:
    ops = _ops()
    window = resolve_reporting_window(payload.get("month") or None, int(payload["year"]) if payload.get("year") else None)
    clients = ops.list_clients(window.month, window.year)
    latest = latest_successful_run_urls(
        ops.services["sheets"],
        ops.control_sheet_id,
        ops.runs_sheet,
        window.month,
        window.year,
    )
    missing = [
        client
        for client in clients
        if client.get("active") and not latest.get(client["client_key"])
    ]
    return {
        "status": "ok",
        "period": f"{window.month} {window.year}",
        "prev_period": f"{window.prev_month} {window.prev_year}",
        "clients": clients,
        "missing_clients": missing,
    }


def _alpha_geo_performance(payload: dict[str, Any]) -> dict[str, Any]:
    ops = _ops()
    clients = [client for client in ops.load_clients(active_only=False) if client.client_name.casefold() == "alpha funded"]
    if len(clients) != 1:
        raise ValueError("Expected exactly one Alpha Funded client in the control sheet.")
    client = clients[0]
    if client.source_currency != "USD":
        raise ValueError("Alpha Funded source currency is not USD; this page requires currency conversion.")
    return load_alpha_geo_snapshot(ops.services["sheets"], client.spreadsheet_id, client.campaigns_tab)


def _create_client(payload: dict[str, Any]) -> dict[str, Any]:
    created = _ops().create_client(
        client_name=str(payload.get("client_name", "")),
        client_key=str(payload.get("client_key", "")),
        template_presentation_url_or_id=str(payload.get("template_presentation_url_or_id", "")),
        parent_folder_id=str(payload.get("parent_folder_id", "")),
        active=_parse_bool(payload.get("active", False)),
        timezone=str(payload.get("timezone", "America/New_York")),
        insights_provider=str(payload.get("insights_provider", "auto")),
        source_currency=str(payload.get("source_currency", "USD")),
        report_currency=str(payload.get("report_currency", "USD")),
        fx_policy=str(payload.get("fx_policy", "none")),
    )
    return {"status": "ok", "client": created}


def _set_active(payload: dict[str, Any]) -> dict[str, Any]:
    result = _ops().set_client_active(
        str(payload.get("client_key", "")),
        _parse_bool(payload.get("active", True)),
    )
    return {"status": "ok", "client": result}


def _preflight(payload: dict[str, Any]) -> dict[str, Any]:
    result = _ops().preflight_report(
        client_key=str(payload.get("client_key", "")),
        month=str(payload.get("month", "")),
        year=int(payload.get("year", 0)),
        allow_first_month_baseline=_parse_bool(payload.get("allow_first_month_baseline", False)),
        include_inactive=_parse_bool(payload.get("include_inactive", True)),
    )
    return {"status": "ok", "preflight": result}


def _run_report(payload: dict[str, Any]) -> dict[str, Any]:
    run_mode = str(payload.get("run_mode", "one")).strip().lower()
    selected_client_keys = [
        str(value).strip()
        for value in payload.get("selected_client_keys", [])
        if str(value).strip()
    ]
    base_cmd = [
        sys.executable,
        "tools/run_control_sheet_reports.py",
        "--run-mode",
        "one" if selected_client_keys else run_mode,
        "--month",
        str(payload.get("month", "")),
        "--year",
        str(payload.get("year", "")),
        "--insights-provider",
        str(payload.get("insights_provider", "auto") or "auto"),
    ]
    if _parse_bool(payload.get("allow_first_month_baseline", False)):
        base_cmd.append("--allow-first-month-baseline")
    if _parse_bool(payload.get("include_inactive", False)):
        base_cmd.append("--include-inactive")
    if payload.get("prev_month"):
        base_cmd.extend(["--prev-month", str(payload["prev_month"])])
    if payload.get("prev_year"):
        base_cmd.extend(["--prev-year", str(payload["prev_year"])])
    if payload.get("next_month"):
        base_cmd.extend(["--next-month", str(payload["next_month"])])
    if payload.get("next_year"):
        base_cmd.extend(["--next-year", str(payload["next_year"])])

    runs = []
    keys = selected_client_keys or [str(payload.get("client_key", "")).strip()]
    if selected_client_keys or run_mode == "one":
        for key in keys:
            if not key:
                raise ValueError("client_key is required when run_mode is one.")
            cmd = [*base_cmd, "--client-key", key]
            runs.append(_run_subprocess(cmd))
    else:
        runs.append(_run_subprocess(base_cmd))
    return {"status": "ok", "runs": runs}


def _run_subprocess(cmd: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        cmd,
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
        timeout=int(os.environ.get("REPORT_PORTAL_RUN_TIMEOUT_SECONDS", "600")),
        check=False,
    )
    stdout = completed.stdout.strip()
    try:
        payload = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        payload = {"raw_stdout": stdout}
    if completed.returncode != 0:
        return {
            "status": "error",
            "exit_code": completed.returncode,
            "payload": payload,
            "stderr": completed.stderr.strip(),
        }
    return {"status": "ok", "payload": payload}


from tools.benchmarks.cli import dispatch as benchmark_dispatch


COMMANDS = {
    **{command: (lambda payload, command=command: benchmark_dispatch(command, payload)) for command in ("benchmark-list", "benchmark-access", "benchmark-read", "benchmark-passwords")},
    "dashboard": _dashboard,
    "alpha-geo-performance": _alpha_geo_performance,
    "create-client": _create_client,
    "set-active": _set_active,
    "preflight": _preflight,
    "run-report": _run_report,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run MT portal ops actions as JSON.")
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("--payload", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = _load_payload(args)
        result = COMMANDS[args.command](payload)
        print(json.dumps(result, indent=2, default=str))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
