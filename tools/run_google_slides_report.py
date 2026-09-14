#!/usr/bin/env python3
"""Generate a monthly report from Google Sheets into a copied Google Slides deck."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.calculate_kpis import build_full_kpi_report
from tools.currency_conversion import (
    convert_dataframe_monetary_values,
    convert_manual_money_values,
    normalize_currency,
    normalize_fx_policy,
    resolve_fx_conversion,
)
from tools.generate_insights import INSIGHT_PROVIDER_CHOICES, generate_insights_with_provider
from tools.google_sheet_report_data import (
    append_run_log,
    load_report_sheet,
    make_run_log_row,
    read_manual_inputs,
    write_kpi_output,
)
from tools.google_slides_report import (
    audit_placeholders,
    build_slides_replacements,
    copy_presentation,
    export_presentation,
    get_slide_thumbnail_urls,
    insert_creative_metric_tables,
    read_placeholders,
    refresh_linked_sheets_charts,
    replace_placeholders,
)
from tools.google_workspace import build_workspace_services, extract_file_id
from tools.report_periods import resolve_reporting_window
from tools.report_insights import assert_insights_shape, build_fake_insights
from tools.report_replacements import build_audit_replacements
from tools.validate_data import canonicalize_traffic_sources, validate_or_raise

PDF_MIME = "application/pdf"
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
MIN_SUPPORTED_PYTHON = (3, 11)


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Google Sheets -> Google Slides report pipeline.")
    parser.add_argument("--spreadsheet", default="", help="Google Sheet URL or ID")
    parser.add_argument("--template-presentation", required=True, help="Google Slides template URL or ID")
    parser.add_argument("--client", required=True)
    parser.add_argument("--month", required=True)
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--prev-month", default="")
    parser.add_argument("--prev-year", type=int, default=None)
    parser.add_argument("--next-month", default="")
    parser.add_argument("--next-year", type=int, default=None)
    parser.add_argument("--campaigns-sheet", default="Campaigns")
    parser.add_argument("--ads-sheet", default="Ads")
    parser.add_argument("--manual-inputs-sheet", default="Manual Inputs")
    parser.add_argument("--kpi-output-sheet", default="KPI Output")
    parser.add_argument("--run-log-sheet", default="Run Log")
    parser.add_argument("--output-folder-id", default=os.environ.get("GOOGLE_DRIVE_OUTPUT_FOLDER_ID", ""))
    parser.add_argument("--output-title", default="")
    parser.add_argument("--company-revenue", type=float, default=None)
    parser.add_argument("--ad-revenue", type=float, default=None)
    parser.add_argument("--ad-cost", type=float, default=None)
    parser.add_argument("--prev-company-revenue", type=float, default=None)
    parser.add_argument("--prev-ad-revenue", type=float, default=None)
    parser.add_argument("--prev-ad-cost", type=float, default=None)
    parser.add_argument(
        "--currency",
        choices=["USD", "EUR", "usd", "eur"],
        default=os.environ.get("REPORT_CURRENCY", "USD"),
        help="Currency symbol used for placeholder-backed money values and generated narratives.",
    )
    parser.add_argument(
        "--source-currency",
        default=os.environ.get("REPORT_SOURCE_CURRENCY", ""),
        help="Currency used by source Sheet money fields (USD or MXN).",
    )
    parser.add_argument(
        "--report-currency",
        default=os.environ.get("REPORT_CURRENCY", ""),
        help="Currency shown in the completed report (USD, EUR, or MXN).",
    )
    parser.add_argument(
        "--fx-policy",
        default=os.environ.get("REPORT_FX_POLICY", "none"),
        help="Currency conversion policy: none or banxico_monthly_average.",
    )
    parser.add_argument("--media-buyer-notes", default="")
    parser.add_argument("--special-requests", default="")
    parser.add_argument(
        "--insights-provider",
        choices=sorted(INSIGHT_PROVIDER_CHOICES),
        default=os.environ.get("REPORT_INSIGHTS_PROVIDER", "auto"),
        help="Narrative provider. 'auto' requires Anthropic or OpenAI and never falls back to deterministic.",
    )
    parser.add_argument("--use-claude", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--audit-only", action="store_true", help="Audit template tokens without copying or editing.")
    parser.add_argument("--skip-run-log", action="store_true")
    parser.add_argument("--skip-kpi-output", action="store_true")
    parser.add_argument("--skip-chart-refresh", action="store_true")
    parser.add_argument(
        "--allow-first-month-baseline",
        action="store_true",
        default=_env_flag("ALLOW_FIRST_MONTH_BASELINE"),
        help="Allow generation when current-month data exists but the previous month is empty, using zero previous KPIs.",
    )
    parser.add_argument("--thumbnail-audit", action="store_true", help="Print thumbnail URLs for quick visual checks.")
    parser.add_argument("--export-pdf-path", default="")
    parser.add_argument("--export-pptx-path", default="")
    return parser.parse_args()


def build_run_namespace(**overrides) -> argparse.Namespace:
    values = {
        "spreadsheet": "",
        "template_presentation": "",
        "client": "",
        "month": "",
        "year": 0,
        "prev_month": "",
        "prev_year": None,
        "next_month": "",
        "next_year": None,
        "campaigns_sheet": "Campaigns",
        "ads_sheet": "Ads",
        "manual_inputs_sheet": "Manual Inputs",
        "kpi_output_sheet": "KPI Output",
        "run_log_sheet": "Run Log",
        "output_folder_id": os.environ.get("GOOGLE_DRIVE_OUTPUT_FOLDER_ID", ""),
        "output_title": "",
        "company_revenue": None,
        "ad_revenue": None,
        "ad_cost": None,
        "prev_company_revenue": None,
        "prev_ad_revenue": None,
        "prev_ad_cost": None,
        "currency": os.environ.get("REPORT_CURRENCY", "USD"),
        "source_currency": os.environ.get("REPORT_SOURCE_CURRENCY", ""),
        "report_currency": os.environ.get("REPORT_CURRENCY", ""),
        "fx_policy": os.environ.get("REPORT_FX_POLICY", "none"),
        "media_buyer_notes": "",
        "special_requests": "",
        "insights_provider": os.environ.get("REPORT_INSIGHTS_PROVIDER", "auto"),
        "use_claude": False,
        "audit_only": False,
        "skip_run_log": False,
        "skip_kpi_output": False,
        "skip_chart_refresh": False,
        "allow_first_month_baseline": _env_flag("ALLOW_FIRST_MONTH_BASELINE"),
        "thumbnail_audit": False,
        "export_pdf_path": "",
        "export_pptx_path": "",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _manual_or_arg(
    manual: dict,
    args: argparse.Namespace,
    key: str,
    default: float = 0.0,
    manual_key: str | None = None,
) -> float:
    cli_value = getattr(args, key.replace("-", "_"), None)
    if cli_value is not None:
        return cli_value
    lookup = manual_key or key
    value = manual.get(lookup.replace("-", "_"), manual.get(lookup, default))
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _resolve_currency(manual: dict, args: argparse.Namespace) -> str:
    value = (
        getattr(args, "report_currency", None)
        or getattr(args, "currency", None)
        or manual.get("currency")
        or manual.get("Currency")
        or "USD"
    )
    return normalize_currency(value)


def _resolve_source_currency(args: argparse.Namespace, report_currency: str) -> str:
    return normalize_currency(getattr(args, "source_currency", "") or report_currency)


def _resolve_fx_policy(args: argparse.Namespace) -> str:
    return normalize_fx_policy(getattr(args, "fx_policy", "none"))


def ensure_supported_python_version() -> None:
    if sys.version_info < MIN_SUPPORTED_PYTHON:
        wanted = ".".join(str(part) for part in MIN_SUPPORTED_PYTHON)
        current_info = tuple(sys.version_info[:3])
        current = ".".join(str(part) for part in current_info)
        raise RuntimeError(
            f"Python {wanted}+ is required for launch readiness. Current runtime is {current}. "
            "Upgrade the interpreter or run the container/CI image based on Python 3.11+."
        )


def resolve_requested_provider(args: argparse.Namespace) -> str:
    provider = getattr(args, "insights_provider", "auto")
    if getattr(args, "use_claude", False):
        if provider not in {"", "deterministic", "anthropic"}:
            raise ValueError("--use-claude cannot be combined with a non-Anthropic insights provider.")
        provider = "anthropic"
    normalized = (provider or "auto").strip().lower()
    if normalized not in INSIGHT_PROVIDER_CHOICES:
        raise ValueError(
            f"Unsupported insights provider {provider!r}. Expected one of {sorted(INSIGHT_PROVIDER_CHOICES)}."
        )
    return normalized


def validate_runtime_inputs(args: argparse.Namespace) -> None:
    if not args.audit_only and not args.spreadsheet:
        raise ValueError("--spreadsheet is required unless --audit-only is set")
    if args.audit_only:
        return
    provider = resolve_requested_provider(args)
    if provider == "auto" and not (
        os.environ.get("ANTHROPIC_API_KEY", "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()
    ):
        raise EnvironmentError("INSIGHTS_PROVIDER=auto requires ANTHROPIC_API_KEY or OPENAI_API_KEY.")
    if provider == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        raise EnvironmentError("ANTHROPIC_API_KEY is required when insights provider is 'anthropic'.")
    if provider == "openai" and not os.environ.get("OPENAI_API_KEY", "").strip():
        raise EnvironmentError("OPENAI_API_KEY is required when insights provider is 'openai'.")


def ensure_report_data_available(df, sheet_name: str, client: str, month: str, year: int) -> None:
    is_empty = bool(getattr(df, "empty", False)) if hasattr(df, "empty") else len(df) == 0
    if is_empty:
        raise ValueError(
            f"No report data found in {sheet_name!r} for client {client!r} and period {month} {year}. "
            "Load closed data into both Campaigns and Ads before generating this report."
        )


def _is_empty_frame(df) -> bool:
    return bool(getattr(df, "empty", False)) if hasattr(df, "empty") else len(df) == 0


def _empty_like(df):
    return df.iloc[0:0].copy() if hasattr(df, "iloc") else []


def _first_month_baseline_validation(prev_month: str, prev_year: int) -> dict:
    return {
        "first_month_baseline": True,
        "message": (
            f"No rows found for previous period {prev_month} {prev_year}; "
            "using zero previous-period KPI baseline."
        ),
    }


def run_report(args: argparse.Namespace, services: dict | None = None) -> dict:
    validate_runtime_inputs(args)
    window = resolve_reporting_window(
        args.month,
        args.year,
        prev_month=args.prev_month or None,
        prev_year=args.prev_year,
        next_month=args.next_month or None,
        next_year=args.next_year,
    )
    requested_provider = resolve_requested_provider(args)
    template_id = extract_file_id(args.template_presentation)
    services = services or build_workspace_services()

    if args.audit_only:
        replacements = build_audit_replacements(
            args.client,
            window.month,
            window.year,
            window.prev_month,
            window.next_month,
        )
        template_placeholders = read_placeholders(services["slides"], template_id)
        audit = audit_placeholders(template_placeholders, set(replacements))
        return {
            "status": "audit_ok",
            "client": args.client,
            "period": f"{window.month} {window.year}",
            "audit": audit,
            "replacement_count": len(replacements),
        }

    spreadsheet_id = extract_file_id(args.spreadsheet)
    report_currency = _resolve_currency({}, args)
    source_currency = _resolve_source_currency(args, report_currency)
    fx_policy = _resolve_fx_policy(args)
    current_fx = resolve_fx_conversion(
        source_currency,
        report_currency,
        fx_policy,
        window.month,
        window.year,
    )
    prev_fx = resolve_fx_conversion(
        source_currency,
        report_currency,
        fx_policy,
        window.prev_month,
        window.prev_year,
    )

    campaigns = load_report_sheet(
        services["sheets"],
        spreadsheet_id,
        args.campaigns_sheet,
        args.client,
        month=window.month,
        year=window.year,
    )
    ads = load_report_sheet(
        services["sheets"],
        spreadsheet_id,
        args.ads_sheet,
        args.client,
        month=window.month,
        year=window.year,
    )
    campaigns = canonicalize_traffic_sources(convert_dataframe_monetary_values(campaigns, current_fx))
    ads = canonicalize_traffic_sources(convert_dataframe_monetary_values(ads, current_fx))
    ensure_report_data_available(campaigns, args.campaigns_sheet, args.client, window.month, window.year)
    ensure_report_data_available(ads, args.ads_sheet, args.client, window.month, window.year)
    checkpoints = validate_or_raise(campaigns)
    kpis = build_full_kpi_report(campaigns, ads)

    prev_campaigns = load_report_sheet(
        services["sheets"],
        spreadsheet_id,
        args.campaigns_sheet,
        args.client,
        month=window.prev_month,
        year=window.prev_year,
    )
    prev_ads = load_report_sheet(
        services["sheets"],
        spreadsheet_id,
        args.ads_sheet,
        args.client,
        month=window.prev_month,
        year=window.prev_year,
    )
    prev_campaigns = canonicalize_traffic_sources(convert_dataframe_monetary_values(prev_campaigns, prev_fx))
    prev_ads = canonicalize_traffic_sources(convert_dataframe_monetary_values(prev_ads, prev_fx))
    prev_campaigns_empty = _is_empty_frame(prev_campaigns)
    prev_ads_empty = _is_empty_frame(prev_ads)
    first_month_baseline = False
    if prev_campaigns_empty or prev_ads_empty:
        if getattr(args, "allow_first_month_baseline", False) and prev_campaigns_empty and prev_ads_empty:
            first_month_baseline = True
            prev_checkpoints = _first_month_baseline_validation(window.prev_month, window.prev_year)
            prev_kpis = build_full_kpi_report(_empty_like(campaigns), _empty_like(ads))
        else:
            ensure_report_data_available(
                prev_campaigns,
                args.campaigns_sheet,
                args.client,
                window.prev_month,
                window.prev_year,
            )
            ensure_report_data_available(
                prev_ads,
                args.ads_sheet,
                args.client,
                window.prev_month,
                window.prev_year,
            )
            raise RuntimeError("Previous-period data validation failed unexpectedly.")
    else:
        prev_checkpoints = validate_or_raise(prev_campaigns)
        prev_kpis = build_full_kpi_report(prev_campaigns, prev_ads)

    manual_inputs = read_manual_inputs(
        services["sheets"],
        spreadsheet_id,
        args.manual_inputs_sheet,
        args.client,
        window.month,
        window.year,
    )
    prev_manual_inputs = read_manual_inputs(
        services["sheets"],
        spreadsheet_id,
        args.manual_inputs_sheet,
        args.client,
        window.prev_month,
        window.prev_year,
    )
    manual_inputs = convert_manual_money_values(manual_inputs, current_fx)
    prev_manual_inputs = convert_manual_money_values(prev_manual_inputs, prev_fx)
    overrides = {
        "company_revenue": 0,
        "ad_revenue": _manual_or_arg(manual_inputs, args, "ad_revenue"),
        "ad_cost": _manual_or_arg(manual_inputs, args, "ad_cost"),
        "prev_company_revenue": 0,
        "prev_ad_revenue": _manual_or_arg(
            prev_manual_inputs,
            args,
            "prev_ad_revenue",
            manual_key="ad_revenue",
        ),
        "prev_ad_cost": _manual_or_arg(
            prev_manual_inputs,
            args,
            "prev_ad_cost",
            manual_key="ad_cost",
        ),
    }
    currency = report_currency
    overrides["currency"] = currency

    if not args.skip_kpi_output:
        write_kpi_output(services["sheets"], spreadsheet_id, kpis, sheet_name=args.kpi_output_sheet)

    insights, used_provider = generate_insights_with_provider(
        requested_provider,
        client=args.client,
        month=window.month,
        year=window.year,
        prev_month=window.prev_month,
        prev_year=window.prev_year,
        kpis=kpis,
        user_overrides=overrides,
        media_buyer_notes=args.media_buyer_notes or str(manual_inputs.get("media_buyer_notes", "")),
        special_requests=args.special_requests or str(manual_inputs.get("special_requests", "")),
        currency=currency,
        deterministic_factory=lambda: build_fake_insights(
            kpis,
            args.client,
            window.month,
            window.year,
            window.next_month,
            currency,
        ),
    )
    assert_insights_shape(insights)
    if requested_provider == "auto" and used_provider != "auto":
        insights_mode = f"auto->{used_provider}"
    else:
        insights_mode = used_provider

    replacements = build_slides_replacements(
        args.client,
        window.month,
        window.year,
        window.prev_month,
        window.next_month,
        kpis,
        insights,
        overrides,
        prev_kpis=prev_kpis,
    )

    template_placeholders = read_placeholders(services["slides"], template_id)
    audit = audit_placeholders(template_placeholders, set(replacements))
    if audit["missing_values"]:
        raise ValueError(
            "Template has placeholders that this pipeline cannot fill: "
            + ", ".join(audit["missing_values"])
        )

    output_folder_id = extract_file_id(args.output_folder_id) if args.output_folder_id else None

    title = args.output_title or f"{args.client} {window.month} {window.year} Report"
    copied = copy_presentation(
        services["drive"],
        template_id,
        title,
        folder_id=output_folder_id,
    )
    occurrences = replace_placeholders(services["slides"], copied["id"], replacements)
    inserted_table_requests = insert_creative_metric_tables(services["slides"], copied["id"], kpis)
    refreshed_charts = 0 if args.skip_chart_refresh else refresh_linked_sheets_charts(services["slides"], copied["id"])
    remaining = sorted(read_placeholders(services["slides"], copied["id"]))

    pdf_path = ""
    pptx_path = ""
    if args.export_pdf_path:
        pdf_path = str(export_presentation(services["drive"], copied["id"], args.export_pdf_path, PDF_MIME))
    if args.export_pptx_path:
        pptx_path = str(export_presentation(services["drive"], copied["id"], args.export_pptx_path, PPTX_MIME))

    thumbnail_urls = []
    if args.thumbnail_audit:
        thumbnail_urls = get_slide_thumbnail_urls(services["slides"], copied["id"])

    status = "ok" if not remaining else "needs_review"
    if not args.skip_run_log:
        append_run_log(
            services["sheets"],
            spreadsheet_id,
            make_run_log_row(
                args.client,
                window.month,
                window.year,
                status,
                presentation_url=copied["webViewLink"],
                pdf_path=pdf_path,
                pptx_path=pptx_path,
                remaining_placeholders=remaining,
                validation={
                    "checkpoints": checkpoints,
                    "prev_checkpoints": prev_checkpoints,
                    "requested_insights_provider": requested_provider,
                    "used_insights_provider": used_provider,
                    "prev_period": f"{window.prev_month} {window.prev_year}",
                    "first_month_baseline": first_month_baseline,
                    "fx": {
                        "current": current_fx.as_dict() if current_fx else None,
                        "previous": prev_fx.as_dict() if prev_fx else None,
                    },
                },
            ),
            sheet_name=args.run_log_sheet,
        )

    return {
        "status": status,
        "client": args.client,
        "period": f"{window.month} {window.year}",
        "prev_period": f"{window.prev_month} {window.prev_year}",
        "first_month_baseline": first_month_baseline,
        "presentation": copied,
        "spreadsheet_id": spreadsheet_id,
        "template_presentation_id": template_id,
        "replacement_occurrences": occurrences,
        "inserted_table_requests": inserted_table_requests,
        "refreshed_linked_charts": refreshed_charts,
        "remaining_placeholders": remaining,
        "requested_insights_provider": requested_provider,
        "used_insights_provider": used_provider,
        "insights_mode": insights_mode,
        "currency": currency,
        "source_currency": source_currency,
        "fx_policy": fx_policy,
        "fx": {
            "current": current_fx.as_dict() if current_fx else None,
            "previous": prev_fx.as_dict() if prev_fx else None,
        },
        "template_audit": audit,
        "pdf_path": pdf_path,
        "pptx_path": pptx_path,
        "thumbnail_urls": thumbnail_urls,
    }


def main() -> int:
    args = parse_args()
    ensure_supported_python_version()
    summary = run_report(args)
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
