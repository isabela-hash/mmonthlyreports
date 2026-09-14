"""The geo page must not invent customer-country precision."""
from __future__ import annotations

import pandas as pd
import pytest

from tools.alpha_geo_report import build_snapshot, classify_campaign_geo, metric_values


@pytest.mark.parametrize(
    ("campaign", "expected"),
    [
        ("MOF - Branded - US", "USA"),
        ("MOF - Branded - All Countries", "Mixed / unassigned"),
        ("TOF - UK + CA", "UK + CA"),
        ("TOF - Canada", "UK + CA"),
        ("TOF - Germany", "Europe"),
        ("TOF - LATAM", "LATAM"),
        ("TOF - India", "India"),
        ("TOF - IN", "India"),
        ("TOF - Dubai", "UAE"),
        ("TOF - South Africa", "Africa"),
        ("TOF - Japan", "Asia"),
        ("TOF - US + India", "Mixed / unassigned"),
        ("TOF - INTN - Broad", "Mixed / unassigned"),
        ("TOF - customer acquisition CAC", "Mixed / unassigned"),
    ],
)
def test_campaign_name_classification(campaign: str, expected: str) -> None:
    assert classify_campaign_geo(campaign) == expected


def test_ratios_use_sums_and_guard_empty_denominators() -> None:
    assert metric_values({"Cost": 120, "Total Revenue": 360, "Sales": 3, "Click": 40, "Leads": 12}) == {
        "cps": 40,
        "cpc": 3,
        "aov": 120,
        "cpl": 10,
        "roas": 3,
    }
    assert metric_values({"Cost": 0, "Total Revenue": 10, "Sales": 0, "Click": 0, "Leads": 0}) == {
        "cps": None,
        "cpc": None,
        "aov": None,
        "cpl": None,
        "roas": None,
    }


def test_six_month_snapshot_reconciles_and_preserves_unassigned() -> None:
    months = ["March", "April", "May", "June", "July", "August"]
    records = []
    for month in months:
        records.extend([
            {"Source": "TOF - US", "Cost": 10, "Total Revenue": 30, "Sales": 1, "Leads": 2, "Click": 10, "Client": "Alpha Funded", "Month": month, "Year": 2026},
            {"Source": "TOF - World", "Cost": 5, "Total Revenue": 5, "Sales": 1, "Leads": 1, "Click": 5, "Client": "Alpha Funded", "Month": month, "Year": 2026},
        ])
    snapshot = build_snapshot(pd.DataFrame(records), "sheet-id")
    assert snapshot["campaign_rows"] == 12
    assert snapshot["overall"]["Cost"] == 90
    assert snapshot["overall_metrics"]["roas"] == pytest.approx(210 / 90)
    assert snapshot["attributed_spend_pct"] == pytest.approx(100 * 60 / 90)
    assert sum(row["Cost"] for row in snapshot["rows"]) == snapshot["overall"]["Cost"]
    assert sum(row["Cost"] for row in snapshot["rows"] if row["region"] == "Mixed / unassigned") == 30


def test_missing_month_fails_closed() -> None:
    df = pd.DataFrame([{"Source": "TOF - US", "Cost": 10, "Total Revenue": 20, "Sales": 1, "Leads": 1, "Click": 2, "Client": "Alpha Funded", "Month": "August", "Year": 2026}])
    with pytest.raises(ValueError, match="March 2026"):
        build_snapshot(df, "sheet-id")
