"""Read-only Alpha Funded campaign-name geography check, March–August 2026.

This is a campaign targeting proxy, not a customer-country report. Rows without
one unambiguous geographic label remain unassigned so totals reconcile.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from tools.google_sheet_report_data import load_report_sheet

PERIODS = [(2026, month) for month in range(3, 9)]
MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
REGIONS = ("USA", "UK + CA", "Europe", "LATAM", "India", "Asia", "Africa", "UAE", "Mixed / unassigned")
MEASURES = ("Cost", "Total Revenue", "Click", "Leads", "Sales")

# Deliberately conservative: identify only labels stated in the campaign name.
# UK, India, and UAE are separate buckets, not also counted in Europe or Asia.
GEO_TERMS = {
    "USA": ("US", "USA", "U.S.", "United States"),
    "UK + CA": ("UK", "U.K.", "United Kingdom", "Britain", "Canada", "CA"),
    "Europe": ("Europe", "EU", "European Union", "Germany", "France", "Spain", "Italy", "Netherlands", "Belgium", "Portugal", "Ireland", "Switzerland", "Austria", "Sweden", "Norway", "Denmark", "Finland", "Poland", "Czechia", "Czech Republic", "Greece", "Romania", "Hungary"),
    "LATAM": ("LATAM", "Latin America", "Mexico", "Brazil", "Colombia", "Argentina", "Chile", "Peru", "Ecuador", "Uruguay", "Paraguay", "Bolivia", "Venezuela", "Costa Rica", "Panama", "Guatemala", "Dominican Republic"),
    "India": ("India", "IN"),
    "Asia": ("Asia", "China", "Japan", "South Korea", "Korea", "Singapore", "Malaysia", "Thailand", "Indonesia", "Vietnam", "Philippines", "Pakistan", "Bangladesh", "Taiwan", "Hong Kong"),
    "Africa": ("Africa", "South Africa", "Nigeria", "Kenya", "Egypt", "Morocco", "Ghana"),
    "UAE": ("UAE", "United Arab Emirates", "Dubai", "Abu Dhabi"),
}
GEO_PATTERNS = {
    region: tuple(re.compile(r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])", re.IGNORECASE) for term in terms)
    for region, terms in GEO_TERMS.items()
}


def classify_campaign_geo(source: Any) -> str:
    text = str(source or "")
    matches = [region for region, patterns in GEO_PATTERNS.items() if any(pattern.search(text) for pattern in patterns)]
    return matches[0] if len(matches) == 1 else "Mixed / unassigned"


def metric_values(totals: dict[str, float]) -> dict[str, float | None]:
    cost = totals["Cost"]
    revenue = totals["Total Revenue"]
    sales = totals["Sales"]
    clicks = totals["Click"]
    leads = totals["Leads"]
    return {
        "cps": cost / sales if sales > 0 else None,
        "cpc": cost / clicks if clicks > 0 else None,
        "aov": revenue / sales if sales > 0 else None,
        "cpl": cost / leads if leads > 0 else None,
        "roas": revenue / cost if cost > 0 else None,
    }


def build_snapshot(df: pd.DataFrame, spreadsheet_id: str) -> dict[str, Any]:
    required = {"Source", "Client", "Month", "Year", *MEASURES}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Alpha Funded Campaigns tab is missing columns: {missing}")

    bucket: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {field: 0.0 for field in MEASURES})
    counts: dict[tuple[str, str], int] = defaultdict(int)
    month_counts: dict[str, int] = defaultdict(int)
    for year, month_number in PERIODS:
        month = MONTH_NAMES[month_number - 1]
        monthly = df[
            (df["Client"].astype(str).str.strip() == "Alpha Funded")
            & (df["Month"].astype(str).str.strip().str.lower().isin({month.lower(), f"{month.lower()} {year}"}))
            & (pd.to_numeric(df["Year"], errors="coerce") == year)
        ]
        if monthly.empty:
            raise ValueError(f"Alpha Funded Campaigns has no rows for {month} {year}; six-month check is incomplete.")
        for _, row in monthly.iterrows():
            region = classify_campaign_geo(row["Source"])
            key = (month, region)
            for field in MEASURES:
                value = pd.to_numeric(row[field], errors="coerce")
                if pd.isna(value) or value < 0:
                    raise ValueError(f"Invalid {field} in {month} {year} campaign data.")
                bucket[key][field] += float(value)
            counts[key] += 1
            month_counts[month] += 1

    rows = []
    for _, month_number in PERIODS:
        month = MONTH_NAMES[month_number - 1]
        for region in REGIONS:
            key = (month, region)
            totals = bucket[key]
            rows.append({"month": month, "region": region, "campaign_rows": counts[key], **totals})

    overall = {field: sum(row[field] for row in rows) for field in MEASURES}
    attributed_spend = sum(row["Cost"] for row in rows if row["region"] != "Mixed / unassigned")
    return {
        "status": "ok",
        "client": "Alpha Funded",
        "period": "March–August 2026",
        "months": [MONTH_NAMES[number - 1] for _, number in PERIODS],
        "regions": list(REGIONS),
        "rows": rows,
        "overall": overall,
        "overall_metrics": metric_values(overall),
        "campaign_rows": sum(month_counts.values()),
        "attributed_spend": attributed_spend,
        "attributed_spend_pct": attributed_spend / overall["Cost"] * 100 if overall["Cost"] else None,
        "source_url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
        "read_at_utc": datetime.now(timezone.utc).isoformat(),
        "methodology": "Campaign-name geography only; not actual customer location. Ambiguous, world-wide, and unlabeled campaigns remain Mixed / unassigned. All channels and funnels included. Money is USD. Ratios use six-month sums, not an average of monthly ratios.",
    }


def load_alpha_geo_snapshot(sheets_service: Any, spreadsheet_id: str, campaigns_tab: str = "Campaigns") -> dict[str, Any]:
    df = load_report_sheet(sheets_service, spreadsheet_id, campaigns_tab, "Alpha Funded")
    return build_snapshot(df, spreadsheet_id)
