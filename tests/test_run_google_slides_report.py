import argparse
import json

import pandas as pd
import pytest

from tools import run_google_slides_report as runner


def _sample_args(**overrides):
    values = runner.build_run_namespace(
        template_presentation="template-id",
        client="One Funded",
        month="March",
        year=2026,
        prev_month="February",
        next_month="April",
        insights_provider="deterministic",
    ).__dict__
    values.update(overrides)
    return argparse.Namespace(**values)


def _sample_insights():
    return {
        "slide3_general_insights": "a",
        "slide3_budget_roas": "b",
        "slide3_strategy": "c",
        "google_top_performer": "d",
        "google_main_drop": "e",
        "google_next_steps": "f",
        "meta_top_performer": "g",
        "meta_main_drop": "h",
        "meta_next_steps": "i",
        "google_tof_narrative": "google tof",
        "google_mof_narrative": "google mof",
        "google_bof_narrative": "google bof",
        "meta_tof_narrative": "meta tof",
        "meta_mof_narrative": "meta mof",
        "meta_bof_narrative": "meta bof",
        "bing_tof_narrative": "bing tof",
        "bing_mof_narrative": "bing mof",
        "bing_bof_narrative": "bing bof",
        "performance_manager_narrative": "j",
        "action_items": ["1", "2", "3", "4", "5"],
    }


def _sample_kpis():
    return {
        "google": {"revenue": 1, "cost": 1, "sales": 1, "cps": 1, "roas": 1, "l2s_pct": 1, "cvr_pct": 1, "ctr_pct": 1},
        "meta": {"revenue": 1, "cost": 1, "sales": 1, "cps": 1, "roas": 1, "l2s_pct": 1, "cvr_pct": 1, "ctr_pct": 1},
        "bing": {"revenue": 0, "cost": 0, "sales": 0, "cps": 0, "roas": 0, "l2s_pct": 0, "cvr_pct": 0, "ctr_pct": 0},
        "totals": {"revenue": 2, "cost": 2, "sales": 2, "roas": 1, "cps": 1, "l2s_pct": 1, "cvr_pct": 1, "aov": 1},
        "google_funnels": {},
        "meta_funnels": {},
        "bing_funnels": {},
        "google_funnel_cards": {},
        "meta_funnel_cards": {},
        "bing_funnel_cards": {},
        "google_top_ads": [],
        "meta_top_ads": [],
        "bing_top_ads": [],
        "total_funnel_distribution": {},
    }


def test_validate_runtime_inputs_allows_audit_only_without_spreadsheet():
    runner.validate_runtime_inputs(_sample_args(audit_only=True))


def test_validate_runtime_inputs_requires_spreadsheet_for_non_audit_runs():
    with pytest.raises(ValueError, match="--spreadsheet is required"):
        runner.validate_runtime_inputs(_sample_args())


def test_validate_runtime_inputs_requires_api_key_for_anthropic(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY is required"):
        runner.validate_runtime_inputs(_sample_args(insights_provider="anthropic", spreadsheet="sheet-id"))


def test_validate_runtime_inputs_requires_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(EnvironmentError, match="OPENAI_API_KEY is required"):
        runner.validate_runtime_inputs(_sample_args(insights_provider="openai", spreadsheet="sheet-id"))


def test_validate_runtime_inputs_requires_ai_key_for_auto(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(EnvironmentError, match="INSIGHTS_PROVIDER=auto requires"):
        runner.validate_runtime_inputs(_sample_args(insights_provider="auto", spreadsheet="sheet-id"))


def test_build_run_namespace_defaults_to_auto_provider():
    assert runner.build_run_namespace().insights_provider == "auto"


def test_resolve_requested_provider_promotes_use_claude_alias():
    assert runner.resolve_requested_provider(_sample_args(use_claude=True)) == "anthropic"


def test_ensure_supported_python_version_rejects_old_python(monkeypatch):
    monkeypatch.setattr(runner.sys, "version_info", (3, 9, 6))

    with pytest.raises(RuntimeError, match="Python 3.11\\+ is required"):
        runner.ensure_supported_python_version()


def test_ensure_report_data_available_raises_clear_error_for_empty_period():
    class EmptyFrame:
        empty = True

    with pytest.raises(ValueError, match="No report data found in 'Campaigns'.*April 2026"):
        runner.ensure_report_data_available(EmptyFrame(), "Campaigns", "Top Tier Trader", "April", 2026)


def test_main_audit_only_prints_summary(monkeypatch, capsys):
    monkeypatch.setattr(runner.sys, "version_info", (3, 11, 9))
    monkeypatch.setattr(runner, "parse_args", lambda: _sample_args(audit_only=True))
    monkeypatch.setattr(runner, "build_workspace_services", lambda: {"slides": object()})
    monkeypatch.setattr(runner, "extract_file_id", lambda value: "template-123")
    monkeypatch.setattr(runner, "build_audit_replacements", lambda *args, **kwargs: {"{{CLIENT}}": "One Funded"})
    monkeypatch.setattr(runner, "read_placeholders", lambda *args, **kwargs: {"{{CLIENT}}"})
    monkeypatch.setattr(
        runner,
        "audit_placeholders",
        lambda template_placeholders, available_replacements: {
            "template_placeholders": sorted(template_placeholders),
            "missing_values": [],
            "unused_values": [],
        },
    )

    assert runner.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["audit"]["missing_values"] == []
    assert payload["replacement_count"] == 1


def test_main_raises_when_template_has_missing_values(monkeypatch):
    monkeypatch.setattr(runner.sys, "version_info", (3, 11, 9))
    monkeypatch.setattr(runner, "parse_args", lambda: _sample_args(spreadsheet="sheet-id"))
    monkeypatch.setattr(
        runner,
        "build_workspace_services",
        lambda: {"slides": object(), "sheets": object(), "drive": object()},
    )
    monkeypatch.setattr(runner, "extract_file_id", lambda value: value)
    monkeypatch.setattr(runner, "load_report_sheet", lambda *args, **kwargs: [{"row": 1}])
    monkeypatch.setattr(runner, "validate_or_raise", lambda df: {"checkpoint_1_passed": True})
    monkeypatch.setattr(
        runner,
        "build_full_kpi_report",
        lambda *args, **kwargs: _sample_kpis(),
    )
    monkeypatch.setattr(runner, "read_manual_inputs", lambda *args, **kwargs: {})
    monkeypatch.setattr(runner, "write_kpi_output", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        runner,
        "generate_insights_with_provider",
        lambda *args, **kwargs: (_sample_insights(), "deterministic"),
    )
    monkeypatch.setattr(runner, "build_slides_replacements", lambda *args, **kwargs: {"{{CLIENT}}": "One Funded"})
    monkeypatch.setattr(runner, "read_placeholders", lambda *args, **kwargs: {"{{CLIENT}}", "{{MISSING}}"})
    monkeypatch.setattr(
        runner,
        "audit_placeholders",
        lambda *args, **kwargs: {
            "template_placeholders": ["{{CLIENT}}", "{{MISSING}}"],
            "missing_values": ["{{MISSING}}"],
            "unused_values": [],
        },
    )

    with pytest.raises(ValueError, match="Template has placeholders that this pipeline cannot fill"):
        runner.main()


def test_run_report_uses_prev_year_for_previous_month(monkeypatch):
    monkeypatch.setattr(runner, "build_workspace_services", lambda: {"slides": object(), "sheets": object(), "drive": object()})
    monkeypatch.setattr(runner, "extract_file_id", lambda value: value)
    calls = []

    def fake_load_report_sheet(_service, _spreadsheet_id, sheet_name, _client, month=None, year=None, **_kwargs):
        calls.append((sheet_name, month, year))
        return [{"row": 1}]

    monkeypatch.setattr(runner, "load_report_sheet", fake_load_report_sheet)
    monkeypatch.setattr(runner, "validate_or_raise", lambda df: {"checkpoint_1_passed": True})
    monkeypatch.setattr(
        runner,
        "build_full_kpi_report",
        lambda *args, **kwargs: _sample_kpis(),
    )
    monkeypatch.setattr(runner, "read_manual_inputs", lambda *args, **kwargs: {})
    monkeypatch.setattr(runner, "write_kpi_output", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "generate_insights_with_provider", lambda *args, **kwargs: (_sample_insights(), "deterministic"))
    monkeypatch.setattr(runner, "build_slides_replacements", lambda *args, **kwargs: {"{{CLIENT}}": "One Funded"})
    monkeypatch.setattr(runner, "read_placeholders", lambda *args, **kwargs: {"{{CLIENT}}"})
    monkeypatch.setattr(
        runner,
        "audit_placeholders",
        lambda *args, **kwargs: {"template_placeholders": ["{{CLIENT}}"], "missing_values": [], "unused_values": []},
    )
    monkeypatch.setattr(runner, "copy_presentation", lambda *args, **kwargs: {"id": "deck-1", "webViewLink": "https://deck"})
    monkeypatch.setattr(runner, "replace_placeholders", lambda *args, **kwargs: 1)
    monkeypatch.setattr(runner, "insert_creative_metric_tables", lambda *args, **kwargs: 0)
    monkeypatch.setattr(runner, "refresh_linked_sheets_charts", lambda *args, **kwargs: 0)
    monkeypatch.setattr(runner, "append_run_log", lambda *args, **kwargs: None)

    summary = runner.run_report(
        _sample_args(
            spreadsheet="sheet-id",
            month="January",
            year=2026,
            prev_month="December",
            prev_year=2025,
            next_month="February",
            next_year=2026,
        ),
        services={"slides": object(), "sheets": object(), "drive": object()},
    )

    assert ("Campaigns", "December", 2025) in calls
    assert summary["prev_period"] == "December 2025"


def test_run_report_extracts_output_folder_id_from_url(monkeypatch):
    monkeypatch.setattr(runner, "build_workspace_services", lambda: {"slides": object(), "sheets": object(), "drive": object()})
    monkeypatch.setattr(
        runner,
        "extract_file_id",
        lambda value: "folder-123" if "drive.google.com" in value else value,
    )
    monkeypatch.setattr(runner, "load_report_sheet", lambda *args, **kwargs: [{"row": 1}])
    monkeypatch.setattr(runner, "validate_or_raise", lambda df: {"checkpoint_1_passed": True})
    monkeypatch.setattr(
        runner,
        "build_full_kpi_report",
        lambda *args, **kwargs: _sample_kpis(),
    )
    monkeypatch.setattr(runner, "read_manual_inputs", lambda *args, **kwargs: {})
    monkeypatch.setattr(runner, "write_kpi_output", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "generate_insights_with_provider", lambda *args, **kwargs: (_sample_insights(), "deterministic"))
    monkeypatch.setattr(runner, "build_slides_replacements", lambda *args, **kwargs: {"{{CLIENT}}": "One Funded"})
    monkeypatch.setattr(runner, "read_placeholders", lambda *args, **kwargs: {"{{CLIENT}}"})
    monkeypatch.setattr(
        runner,
        "audit_placeholders",
        lambda *args, **kwargs: {"template_placeholders": ["{{CLIENT}}"], "missing_values": [], "unused_values": []},
    )
    captured = {}

    def fake_copy_presentation(_drive, _template_id, _title, folder_id=None):
        captured["folder_id"] = folder_id
        return {"id": "deck-1", "webViewLink": "https://deck"}

    monkeypatch.setattr(runner, "copy_presentation", fake_copy_presentation)
    monkeypatch.setattr(runner, "replace_placeholders", lambda *args, **kwargs: 1)
    monkeypatch.setattr(runner, "insert_creative_metric_tables", lambda *args, **kwargs: 0)
    monkeypatch.setattr(runner, "refresh_linked_sheets_charts", lambda *args, **kwargs: 0)
    monkeypatch.setattr(runner, "append_run_log", lambda *args, **kwargs: None)

    runner.run_report(
        _sample_args(
            spreadsheet="sheet-id",
            output_folder_id="https://drive.google.com/drive/folders/folder-123?usp=drive_link",
        ),
        services={"slides": object(), "sheets": object(), "drive": object()},
    )

    assert captured["folder_id"] == "folder-123"


def test_run_report_allows_first_month_zero_previous_baseline(monkeypatch):
    monkeypatch.setattr(runner, "build_workspace_services", lambda: {"slides": object(), "sheets": object(), "drive": object()})
    monkeypatch.setattr(runner, "extract_file_id", lambda value: value)
    current = pd.DataFrame([{"Client": "One Funded", "Month": "March", "Year": 2026}])
    previous = current.iloc[0:0].copy()

    def fake_load_report_sheet(_service, _spreadsheet_id, _sheet_name, _client, month=None, **_kwargs):
        return current if month == "March" else previous

    build_lengths = []

    def fake_build_full_kpi_report(campaigns, ads):
        build_lengths.append((len(campaigns), len(ads)))
        return _sample_kpis()

    monkeypatch.setattr(runner, "load_report_sheet", fake_load_report_sheet)
    monkeypatch.setattr(runner, "validate_or_raise", lambda df: {"checkpoint_1_passed": True})
    monkeypatch.setattr(runner, "build_full_kpi_report", fake_build_full_kpi_report)
    monkeypatch.setattr(runner, "read_manual_inputs", lambda *args, **kwargs: {})
    monkeypatch.setattr(runner, "write_kpi_output", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "generate_insights_with_provider", lambda *args, **kwargs: (_sample_insights(), "deterministic"))
    monkeypatch.setattr(runner, "build_slides_replacements", lambda *args, **kwargs: {"{{CLIENT}}": "One Funded"})
    monkeypatch.setattr(runner, "read_placeholders", lambda *args, **kwargs: {"{{CLIENT}}"})
    monkeypatch.setattr(
        runner,
        "audit_placeholders",
        lambda *args, **kwargs: {"template_placeholders": ["{{CLIENT}}"], "missing_values": [], "unused_values": []},
    )
    monkeypatch.setattr(runner, "copy_presentation", lambda *args, **kwargs: {"id": "deck-1", "webViewLink": "https://deck"})
    monkeypatch.setattr(runner, "replace_placeholders", lambda *args, **kwargs: 1)
    monkeypatch.setattr(runner, "insert_creative_metric_tables", lambda *args, **kwargs: 0)
    monkeypatch.setattr(runner, "refresh_linked_sheets_charts", lambda *args, **kwargs: 0)
    monkeypatch.setattr(runner, "append_run_log", lambda *args, **kwargs: None)

    summary = runner.run_report(
        _sample_args(
            spreadsheet="sheet-id",
            allow_first_month_baseline=True,
        ),
        services={"slides": object(), "sheets": object(), "drive": object()},
    )

    assert summary["first_month_baseline"] is True
    assert build_lengths[-1] == (0, 0)
