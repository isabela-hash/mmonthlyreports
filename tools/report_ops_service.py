#!/usr/bin/env python3
"""Minimal internal web UI for triggering monthly report jobs."""
from __future__ import annotations

import json
import os
import sys
from html import escape
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.cloud_run_jobs import CloudRunJobLauncher
from tools.control_sheet import load_control_sheet_clients
from tools.google_workspace import build_workspace_services, extract_file_id
from tools.report_ops import ReportOps
from tools.report_periods import default_reporting_window


def _read_body(environ) -> bytes:
    length = int(environ.get("CONTENT_LENGTH") or "0")
    return environ["wsgi.input"].read(length)


def _wants_json(environ) -> bool:
    accept = environ.get("HTTP_ACCEPT", "")
    content_type = environ.get("CONTENT_TYPE", "")
    return "application/json" in accept or "application/json" in content_type


def _parse_request_payload(environ) -> dict[str, str]:
    body = _read_body(environ)
    content_type = environ.get("CONTENT_TYPE", "")
    if "application/json" in content_type:
        raw = json.loads(body.decode("utf-8") or "{}")
        return {str(key): str(value) for key, value in raw.items() if value is not None}
    parsed = parse_qs(body.decode("utf-8"))
    return {key: values[0] for key, values in parsed.items() if values}


def _parse_bool(value: str, default: bool = False) -> bool:
    if value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_run_request(payload: dict[str, str]) -> dict[str, str]:
    run_mode = payload.get("run_mode", "all").strip().lower() or "all"
    if run_mode not in {"all", "one", "missing"}:
        raise ValueError("run_mode must be 'all', 'one', or 'missing'.")
    client_key = payload.get("client_key", "").strip()
    if run_mode == "one" and not client_key:
        raise ValueError("client_key is required when run_mode is 'one'.")
    month = payload.get("month", "").strip()
    year = payload.get("year", "").strip()
    insights_provider = payload.get("insights_provider", "auto").strip().lower() or "auto"
    if not month or not year:
        raise ValueError("month and year are required.")
    return {
        "run_mode": run_mode,
        "client_key": client_key,
        "month": month,
        "year": year,
        "insights_provider": insights_provider,
        "allow_first_month_baseline": "true" if _parse_bool(payload.get("allow_first_month_baseline", "")) else "false",
        "include_inactive": "true" if _parse_bool(payload.get("include_inactive", "")) else "false",
    }


def _make_env_overrides(payload: dict[str, str]) -> dict[str, str]:
    return {
        "RUN_MODE": payload["run_mode"],
        "CLIENT_KEY": payload["client_key"],
        "REPORT_MONTH": payload["month"],
        "REPORT_YEAR": payload["year"],
        "INSIGHTS_PROVIDER": payload["insights_provider"],
        "ALLOW_FIRST_MONTH_BASELINE": payload["allow_first_month_baseline"],
        "INCLUDE_INACTIVE": payload["include_inactive"],
    }


def render_dashboard_html(clients: list[dict], message: str = "", error: str = "") -> str:
    default_window = default_reporting_window()
    options = "\n".join(
        f'<option value="{escape(client["client_key"])}">{escape(client["client_name"])}</option>'
        for client in clients
    )
    rows = "\n".join(
        "<tr>"
        f"<td>{escape(client.get('client_name', ''))}</td>"
        f"<td>{escape(client.get('client_key', ''))}</td>"
        f"<td>{'active' if client.get('active', True) else 'inactive'}</td>"
        f"<td>{_report_link(client.get('latest_report_url', ''))}</td>"
        "</tr>"
        for client in clients
    )
    message_html = f"<p style='color: green;'>{escape(message)}</p>" if message else ""
    error_html = f"<p style='color: #b00020;'>{escape(error)}</p>" if error else ""
    client_count = len(clients)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Monthly Report Control Panel</title>
    <style>
      body {{ font-family: Georgia, serif; margin: 2rem auto; max-width: 1060px; padding: 0 1rem; background: #f7f3ec; color: #222; }}
      .card {{ background: white; border-radius: 8px; padding: 1.25rem; box-shadow: 0 12px 32px rgba(0,0,0,0.08); margin-bottom: 1rem; }}
      label {{ display: block; margin-top: 1rem; font-weight: 600; }}
      input, select {{ width: 100%; padding: 0.75rem; margin-top: 0.35rem; border-radius: 10px; border: 1px solid #d7c9b8; }}
      .row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
      .row-3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; }}
      button {{ margin-top: 1rem; background: #0a6c74; color: white; border: 0; border-radius: 999px; padding: 0.85rem 1.2rem; cursor: pointer; }}
      small {{ color: #555; }}
      table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
      th, td {{ border-bottom: 1px solid #e9dfd3; padding: 0.65rem; text-align: left; }}
      th {{ background: #faf7f2; }}
    </style>
  </head>
  <body>
    <div class="card">
      <h1>Monthly Report Control Panel</h1>
      <p>{client_count} clients loaded from the master control sheet.</p>
      {message_html}
      {error_html}
      <table>
        <thead><tr><th>Client</th><th>Key</th><th>Status</th><th>Latest report</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>

    <div class="card">
      <h2>Run Reports</h2>
      <form method="post" action="/runs">
        <label for="run_mode">Run mode</label>
        <select id="run_mode" name="run_mode">
          <option value="all">Run all clients</option>
          <option value="one">Run one client</option>
          <option value="missing">Run missing reports</option>
        </select>

        <label for="client_key">Client</label>
        <select id="client_key" name="client_key">
          <option value="">Select a client for single-run mode</option>
          {options}
        </select>

        <div class="row">
          <label for="month">Report month
            <input id="month" name="month" value="{escape(default_window.month)}">
          </label>
          <label for="year">Report year
            <input id="year" name="year" value="{default_window.year}">
          </label>
        </div>

        <label for="insights_provider">Insights provider</label>
        <select id="insights_provider" name="insights_provider">
          <option value="auto">auto</option>
          <option value="anthropic">anthropic</option>
          <option value="openai">openai</option>
          <option value="deterministic">deterministic</option>
        </select>
        <small>Use auto for real runs. It requires Anthropic or OpenAI and does not fall back to deterministic.</small>

        <label>
          <input type="checkbox" name="allow_first_month_baseline" value="true">
          Allow first-month zero previous-period baseline
        </label>
        <label>
          <input type="checkbox" name="include_inactive" value="true">
          Include inactive/staged clients
        </label>

        <button type="submit">Launch run</button>
      </form>
    </div>

    <div class="card">
      <h2>Create Client</h2>
      <form method="post" action="/clients">
        <div class="row">
          <label for="client_name">Client name
            <input id="client_name" name="client_name" placeholder="Lux Algo">
          </label>
          <label for="new_client_key">Client key
            <input id="new_client_key" name="client_key" placeholder="lux-algo">
          </label>
        </div>
        <div class="row">
          <label for="template_presentation_url_or_id">Template presentation
            <input id="template_presentation_url_or_id" name="template_presentation_url_or_id" placeholder="Leave blank to use the standard template">
          </label>
          <label for="parent_folder_id">Parent reports folder
            <input id="parent_folder_id" name="parent_folder_id" placeholder="Leave blank to use the existing reports root">
          </label>
        </div>
        <label>
          <input type="checkbox" name="active" value="true">
          Activate immediately
        </label>
        <button type="submit">Create folder and data Sheet</button>
      </form>
    </div>
  </body>
</html>"""


def _report_link(url: str) -> str:
    return f'<a href="{escape(url)}">Open</a>' if url else ""


def _json_response(start_response, status: str, payload: dict) -> list[bytes]:
    start_response(status, [("Content-Type", "application/json")])
    return [json.dumps(payload, default=str).encode("utf-8")]


def build_app(client_loader: Callable[[], list[dict]], launcher, ops: ReportOps | None = None) -> Callable:
    def app(environ, start_response):
        path = environ.get("PATH_INFO", "/")
        method = environ.get("REQUEST_METHOD", "GET").upper()

        if path == "/healthz":
            start_response("200 OK", [("Content-Type", "application/json")])
            return [b'{"status":"ok"}']

        if path == "/" and method == "GET":
            try:
                clients = ops.list_clients(default_reporting_window().month, default_reporting_window().year) if ops else client_loader()
                body = render_dashboard_html(clients)
                start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            except Exception as exc:
                body = render_dashboard_html([], error=str(exc))
                start_response("500 Internal Server Error", [("Content-Type", "text/html; charset=utf-8")])
            return [body.encode("utf-8")]

        if path == "/clients" and method == "GET":
            try:
                clients = ops.list_clients(default_reporting_window().month, default_reporting_window().year) if ops else client_loader()
                return _json_response(start_response, "200 OK", {"clients": clients})
            except Exception as exc:
                return _json_response(start_response, "500 Internal Server Error", {"status": "error", "error": str(exc)})

        if path == "/clients" and method == "POST":
            try:
                if not ops:
                    raise RuntimeError("Report ops backend is not configured.")
                payload = _parse_request_payload(environ)
                created = ops.create_client(
                    client_name=payload.get("client_name", ""),
                    client_key=payload.get("client_key", ""),
                    template_presentation_url_or_id=payload.get("template_presentation_url_or_id", ""),
                    parent_folder_id=payload.get("parent_folder_id", ""),
                    active=_parse_bool(payload.get("active", "")),
                )
                if _wants_json(environ):
                    return _json_response(start_response, "201 Created", {"status": "created", "client": created})
                clients = ops.list_clients(default_reporting_window().month, default_reporting_window().year)
                body = render_dashboard_html(clients, message=f"Created {created['client_name']}.")
                start_response("201 Created", [("Content-Type", "text/html; charset=utf-8")])
                return [body.encode("utf-8")]
            except Exception as exc:
                if _wants_json(environ):
                    return _json_response(start_response, "400 Bad Request", {"status": "error", "error": str(exc)})
                clients = client_loader()
                body = render_dashboard_html(clients, error=str(exc))
                start_response("400 Bad Request", [("Content-Type", "text/html; charset=utf-8")])
                return [body.encode("utf-8")]

        if path.startswith("/clients/") and path.endswith("/activate") and method == "POST":
            try:
                if not ops:
                    raise RuntimeError("Report ops backend is not configured.")
                client_key = path.split("/")[2]
                payload = _parse_request_payload(environ)
                active = _parse_bool(payload.get("active", "true"), default=True)
                result = ops.set_client_active(client_key, active)
                return _json_response(start_response, "200 OK", {"status": "updated", "client": result})
            except Exception as exc:
                return _json_response(start_response, "400 Bad Request", {"status": "error", "error": str(exc)})

        if path == "/reports/preflight" and method == "POST":
            try:
                if not ops:
                    raise RuntimeError("Report ops backend is not configured.")
                payload = _parse_request_payload(environ)
                result = ops.preflight_report(
                    client_key=payload.get("client_key", ""),
                    month=payload.get("month", ""),
                    year=int(payload.get("year", "0")),
                    allow_first_month_baseline=_parse_bool(payload.get("allow_first_month_baseline", "")),
                    include_inactive=_parse_bool(payload.get("include_inactive", "true"), default=True),
                )
                return _json_response(start_response, "200 OK", result)
            except Exception as exc:
                return _json_response(start_response, "400 Bad Request", {"status": "error", "error": str(exc)})

        if path == "/runs" and method == "POST":
            try:
                payload = _normalize_run_request(_parse_request_payload(environ))
                result = launcher.launch(_make_env_overrides(payload))
                response_payload = {
                    "status": "queued",
                    "operation": result.get("name", ""),
                    "requested": payload,
                }
                if _wants_json(environ):
                    start_response("202 Accepted", [("Content-Type", "application/json")])
                    return [json.dumps(response_payload).encode("utf-8")]
                clients = ops.list_clients(default_reporting_window().month, default_reporting_window().year) if ops else client_loader()
                body = render_dashboard_html(
                    clients,
                    message=f"Run queued successfully. Operation: {response_payload['operation']}",
                )
                start_response("202 Accepted", [("Content-Type", "text/html; charset=utf-8")])
                return [body.encode("utf-8")]
            except Exception as exc:
                if _wants_json(environ):
                    start_response("400 Bad Request", [("Content-Type", "application/json")])
                    return [json.dumps({"status": "error", "error": str(exc)}).encode("utf-8")]
                try:
                    clients = ops.list_clients(default_reporting_window().month, default_reporting_window().year) if ops else client_loader()
                except Exception:
                    clients = []
                body = render_dashboard_html(clients, error=str(exc))
                start_response("400 Bad Request", [("Content-Type", "text/html; charset=utf-8")])
                return [body.encode("utf-8")]

        start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
        return [b"Not found"]

    return app


def load_active_clients_for_dashboard() -> list[dict]:
    services = build_workspace_services()
    control_sheet = os.environ.get("MASTER_CONTROL_SHEET_ID", os.environ.get("CONTROL_SHEET_ID", "")).strip()
    if not control_sheet:
        raise EnvironmentError("MASTER_CONTROL_SHEET_ID or CONTROL_SHEET_ID must be set for the control panel.")
    clients = load_control_sheet_clients(
        services["sheets"],
        extract_file_id(control_sheet),
        sheet_name=os.environ.get("CONTROL_SHEET_CLIENTS_SHEET", "Clients"),
        active_only=True,
    )
    return [{"client_key": client.client_key, "client_name": client.client_name} for client in clients]


def load_clients_for_dashboard() -> list[dict]:
    services = build_workspace_services()
    control_sheet = os.environ.get("MASTER_CONTROL_SHEET_ID", os.environ.get("CONTROL_SHEET_ID", "")).strip()
    if not control_sheet:
        raise EnvironmentError("MASTER_CONTROL_SHEET_ID or CONTROL_SHEET_ID must be set for the control panel.")
    clients = load_control_sheet_clients(
        services["sheets"],
        extract_file_id(control_sheet),
        sheet_name=os.environ.get("CONTROL_SHEET_CLIENTS_SHEET", "Clients"),
        active_only=False,
    )
    return [
        {"client_key": client.client_key, "client_name": client.client_name, "active": client.active}
        for client in clients
    ]


def main() -> int:
    port = int(os.environ.get("PORT", "8080"))
    control_sheet = os.environ.get("MASTER_CONTROL_SHEET_ID", os.environ.get("CONTROL_SHEET_ID", "")).strip()
    ops = ReportOps(
        control_sheet_id=control_sheet,
        clients_sheet=os.environ.get("CONTROL_SHEET_CLIENTS_SHEET", "Clients"),
        runs_sheet=os.environ.get("CONTROL_SHEET_RUNS_SHEET", "Runs"),
    )
    app = build_app(load_clients_for_dashboard, CloudRunJobLauncher(), ops=ops)
    with make_server("0.0.0.0", port, app) as httpd:
        print(f"Monthly report control panel listening on :{port}")
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
