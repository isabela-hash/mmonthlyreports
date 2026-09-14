import argparse

import pytest

from tools import run_control_sheet_reports as batch_runner


def test_validate_args_requires_control_sheet():
    with pytest.raises(ValueError, match="--control-sheet is required"):
        batch_runner.validate_args(argparse.Namespace(control_sheet="", run_mode="all", client_key=""))


def test_main_continues_after_one_client_failure(monkeypatch, capsys):
    monkeypatch.setattr(batch_runner, "ensure_supported_python_version", lambda: None)
    monkeypatch.setattr(
        batch_runner,
        "parse_args",
        lambda: batch_runner.argparse.Namespace(
            control_sheet="control-sheet",
            clients_sheet="Clients",
            runs_sheet="Runs",
            run_mode="all",
            client_key="",
            month="March",
            year=2026,
            prev_month="February",
            prev_year=2026,
            next_month="April",
            next_year=2026,
            insights_provider="deterministic",
            fail_fast=False,
            write_client_run_log=False,
            write_client_kpi_output=False,
            allow_first_month_baseline=False,
            include_inactive=False,
        ),
    )
    monkeypatch.setattr(
        batch_runner,
        "build_workspace_services",
        lambda: {"sheets": object(), "slides": object(), "drive": object()},
    )
    monkeypatch.setattr(batch_runner, "extract_file_id", lambda value: value)
    clients = [
        type(
            "Client",
            (),
            {
                "client_key": "alpha",
                "client_name": "Alpha",
                "spreadsheet_id": "sheet-1",
                "template_presentation_id": "deck-1",
                "output_folder_id": "folder-1",
                "campaigns_tab": "Campaigns",
                "ads_tab": "Ads",
                "insights_provider": "deterministic",
            },
        )(),
        type(
            "Client",
            (),
            {
                "client_key": "beta",
                "client_name": "Beta",
                "spreadsheet_id": "sheet-2",
                "template_presentation_id": "deck-2",
                "output_folder_id": "folder-2",
                "campaigns_tab": "Campaigns",
                "ads_tab": "Ads",
                "insights_provider": "deterministic",
            },
        )(),
    ]
    monkeypatch.setattr(batch_runner, "load_control_sheet_clients", lambda *args, **kwargs: clients)
    monkeypatch.setattr(batch_runner, "select_control_sheet_clients", lambda clients, *_args, **_kwargs: clients)
    monkeypatch.setattr(batch_runner, "append_control_run_log", lambda *args, **kwargs: None)

    def fake_run_report(args, services=None):
        if args.client == "Beta":
            raise ValueError("template mismatch")
        return {
            "status": "ok",
            "client": args.client,
            "presentation": {"webViewLink": "https://deck"},
            "used_insights_provider": "deterministic",
            "remaining_placeholders": [],
            "prev_period": "February 2026",
        }

    monkeypatch.setattr(batch_runner, "run_report", fake_run_report)

    exit_code = batch_runner.main()
    payload = capsys.readouterr().out

    assert exit_code == 1
    assert '"failure_count": 1' in payload
    assert "template mismatch" in payload


def test_select_missing_report_clients_skips_logged_and_drive_existing(monkeypatch):
    clients = [
        type("Client", (), {"client_key": "alpha", "output_folder_id": "folder-1"})(),
        type("Client", (), {"client_key": "beta", "output_folder_id": "folder-2"})(),
        type("Client", (), {"client_key": "gamma", "output_folder_id": "folder-3"})(),
    ]
    monkeypatch.setattr(batch_runner, "_successful_run_keys", lambda *args, **kwargs: {"alpha"})
    monkeypatch.setattr(
        batch_runner,
        "_drive_has_period_deck",
        lambda _drive, client, _month, _year: client.client_key == "beta",
    )

    selected = batch_runner.select_missing_report_clients(
        {"sheets": object(), "drive": object()},
        "control-sheet",
        "Runs",
        clients,
        "May",
        2026,
    )

    assert [client.client_key for client in selected] == ["gamma"]
