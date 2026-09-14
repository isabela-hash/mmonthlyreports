import pytest

from tools.control_sheet import (
    load_control_sheet_clients,
    make_control_run_log_row,
    select_control_sheet_clients,
)


def test_load_control_sheet_clients_parses_active_rows(monkeypatch):
    monkeypatch.setattr(
        "tools.control_sheet.read_sheet_values",
        lambda *args, **kwargs: [
            ["active", "client_name", "client_key", "spreadsheet_url_or_id", "template_presentation_url_or_id", "output_folder_id"],
            ["yes", "One Funded", "one-funded", "sheet-1", "deck-1", "folder-1"],
            ["no", "Dormant", "dormant", "sheet-2", "deck-2", "folder-2"],
        ],
    )

    clients = load_control_sheet_clients(object(), "control-sheet")

    assert len(clients) == 1
    assert clients[0].client_key == "one-funded"
    assert clients[0].campaigns_tab == "Campaigns"
    assert clients[0].insights_provider == "auto"


def test_load_control_sheet_clients_requires_columns(monkeypatch):
    monkeypatch.setattr(
        "tools.control_sheet.read_sheet_values",
        lambda *args, **kwargs: [["client_name"], ["One Funded"]],
    )

    with pytest.raises(ValueError, match="missing required client columns"):
        load_control_sheet_clients(object(), "control-sheet")


def test_load_control_sheet_clients_reads_optional_currency_settings(monkeypatch):
    monkeypatch.setattr(
        "tools.control_sheet.read_sheet_values",
        lambda *args, **kwargs: [
            ["active", "client_name", "client_key", "spreadsheet_url_or_id", "template_presentation_url_or_id", "output_folder_id", "source_currency", "report_currency", "fx_policy"],
            ["yes", "FM Hub", "fm-hub", "sheet-1", "deck-1", "folder-1", "MXN", "USD", "banxico_monthly_average"],
        ],
    )

    client = load_control_sheet_clients(object(), "control-sheet")[0]

    assert client.source_currency == "MXN"
    assert client.report_currency == "USD"
    assert client.fx_policy == "banxico_monthly_average"


def test_select_control_sheet_clients_filters_single_client():
    clients = [
        type("Client", (), {"client_key": "alpha"})(),
        type("Client", (), {"client_key": "beta"})(),
    ]

    selected = select_control_sheet_clients(clients, "one", client_key="beta")

    assert len(selected) == 1
    assert selected[0].client_key == "beta"


def test_make_control_run_log_row_contains_provider_fields():
    client = type(
        "Client",
        (),
        {
            "client_key": "one-funded",
            "client_name": "One Funded",
            "spreadsheet_id": "sheet-1",
        },
    )()

    row = make_control_run_log_row(
        batch_run_id="batch-1",
        run_mode="all",
        client=client,
        month="March",
        year=2026,
        status="ok",
        requested_insights_provider="auto",
        used_insights_provider="deterministic",
    )

    assert row["requested_insights_provider"] == "auto"
    assert row["used_insights_provider"] == "deterministic"
