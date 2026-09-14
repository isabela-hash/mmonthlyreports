# tools/calculate_kpis.py
# NOTE: All revenue values are read from the "Total Revenue" column, not "Revenue" or "Recurring Revenue".
from __future__ import annotations
from typing import Optional
import pandas as pd

def _safe_divide(num: float, den: float, default: float = 0.0) -> float:
    return num / den if den != 0 else default


def _clean_source_name(row) -> str:
    source = row.get("Source", row.get("Source Link", ""))
    if pd.isna(source) or not str(source).strip():
        source = row.get("Source Link", "")
    if pd.isna(source) or not str(source).strip():
        return "N/A"
    return str(source).strip()


def _clean_source_link(row) -> str:
    source_link = row.get("Source Link", "")
    if pd.isna(source_link) or not str(source_link).strip():
        return ""
    return str(source_link).strip()

def calculate_platform_kpis(df: pd.DataFrame, platform: str) -> dict:
    """Calculate aggregate KPIs for a platform (google or meta)."""
    p = df[df["Traffic Source"].str.lower() == platform.lower()]
    cost     = p["Cost"].sum()
    revenue  = p["Total Revenue"].sum()  # Always use Total Revenue
    sales    = p["Sales"].sum()
    leads    = p["Leads"].sum()
    clicks   = p["Click"].sum()
    impr     = p["Impressions"].sum()
    return {
        "cost":     round(cost, 2),
        "revenue":  round(revenue, 2),
        "sales":    round(sales, 0),
        "leads":    round(leads, 0),
        "clicks":   round(clicks, 0),
        "impressions": round(impr, 0),
        "roas":     round(_safe_divide(revenue, cost), 2),
        "cps":      round(_safe_divide(cost, sales), 2),
        "cpl":      round(_safe_divide(cost, leads), 2),
        "l2s_pct":  round(_safe_divide(sales, leads) * 100, 2),
        "cvr_pct":  round(_safe_divide(sales, clicks) * 100, 2),
        "ctr_pct":  round(_safe_divide(clicks, impr) * 100, 2),
        "aov":      round(_safe_divide(revenue, sales), 2),
    }

def calculate_funnel_kpis(df: pd.DataFrame, platform: str) -> dict:
    """Calculate KPIs per funnel (TOF/MOF/BOF) for a platform."""
    p = df[df["Traffic Source"].str.lower() == platform.lower()]
    result = {}
    for funnel in ["TOF", "MOF", "BOF"]:
        f = p[p["Funnel"].str.upper() == funnel]
        if f.empty:
            result[funnel] = {}
            continue
        cost    = f["Cost"].sum()
        revenue = f["Total Revenue"].sum()  # Always use Total Revenue
        sales   = f["Sales"].sum()
        leads   = f["Leads"].sum()
        clicks  = f["Click"].sum()
        impr    = f["Impressions"].sum()
        result[funnel] = {
            "cost":     round(cost, 2),
            "revenue":  round(revenue, 2),
            "sales":    round(sales, 0),
            "leads":    round(leads, 0),
            "clicks":   round(clicks, 0),
            "impressions": round(impr, 0),
            "roas":     round(_safe_divide(revenue, cost), 2),
            "cps":      round(_safe_divide(cost, sales), 2),
            "l2s_pct":  round(_safe_divide(sales, leads) * 100, 2),
            "cvr_pct":  round(_safe_divide(sales, clicks) * 100, 2),
        }
    return result

def calculate_top_ads(df: pd.DataFrame, platform: str, n: int = 10) -> list:
    """Return top N ads by Total Revenue for a platform."""
    p = df[df["Traffic Source"].str.lower() == platform.lower()].copy()
    p = p.sort_values("Total Revenue", ascending=False).head(n)  # Sort by Total Revenue
    results = []
    for _, row in p.iterrows():
        cost    = float(row.get("Cost", 0))
        revenue = float(row.get("Total Revenue", 0))  # Always use Total Revenue
        sales   = float(row.get("Sales", 0))
        results.append({
            "source":  _clean_source_name(row),
            "source_link": _clean_source_link(row),
            "funnel":  str(row.get("Funnel", "")),
            "cost":    round(cost, 2),
            "revenue": round(revenue, 2),
            "sales":   round(sales, 0),
            "roas":    round(_safe_divide(revenue, cost), 2),
        })
    return results


def _detailed_ad_row(row, revenue_total: float = 0.0) -> dict:
    cost = float(row.get("Cost", 0) or 0)
    revenue = float(row.get("Total Revenue", 0) or 0)
    sales = float(row.get("Sales", 0) or 0)
    leads = float(row.get("Leads", 0) or 0)
    clicks = float(row.get("Click", 0) or 0)
    impressions = float(row.get("Impressions", 0) or 0)
    return {
        "source": _clean_source_name(row),
        "source_link": _clean_source_link(row),
        "traffic_source": str(row.get("Traffic Source", "") or "").strip(),
        "funnel": str(row.get("Funnel", "") or "").strip().upper(),
        "cost": round(cost, 2),
        "revenue": round(revenue, 2),
        "revenue_pct": round(_safe_divide(revenue, revenue_total) * 100, 2),
        "sales": round(sales, 0),
        "clicks": round(clicks, 0),
        "leads": round(leads, 0),
        "impressions": round(impressions, 0),
        "roas": round(_safe_divide(revenue, cost), 2),
        "cps": round(_safe_divide(cost, sales), 2),
        "cvr_pct": round(_safe_divide(sales, clicks) * 100, 2),
        "ctr_pct": round(_safe_divide(clicks, impressions) * 100, 2),
    }


def calculate_detailed_top_meta_ads(df: pd.DataFrame, n: int = 10) -> list:
    """Return top Meta ads by Total Revenue with slide-table metrics."""
    p = df[df["Traffic Source"].str.lower() == "meta"].copy()
    revenue_total = float(p["Total Revenue"].sum() or 0)
    p = p.sort_values(["Total Revenue", "Sales"], ascending=[False, False]).head(n)
    return [_detailed_ad_row(row, revenue_total) for _, row in p.iterrows()]


def calculate_top_ads_by_funnel_stage(df: pd.DataFrame, n: int = 3) -> dict:
    """Return top N ad rows by Total Revenue for each funnel stage across all channels."""
    result = {}
    for funnel in ["TOF", "MOF", "BOF"]:
        f = df[df["Funnel"].str.upper() == funnel].copy()
        f = f.sort_values(["Total Revenue", "Sales"], ascending=[False, False]).head(n)
        result[funnel] = [_detailed_ad_row(row) for _, row in f.iterrows()]
    return result


def calculate_funnel_top_ads(df: pd.DataFrame, platform: str) -> dict:
    """Return the highest-revenue ad row for each funnel stage."""
    p = df[df["Traffic Source"].str.lower() == platform.lower()].copy()
    result = {}
    for funnel in ["TOF", "MOF", "BOF"]:
        f = p[p["Funnel"].str.upper() == funnel].copy()
        f = f[f["Total Revenue"] > 0].copy()
        if f.empty:
            result[funnel] = {}
            continue
        f = f.sort_values(["Total Revenue", "Sales"], ascending=[False, False])
        row = f.iloc[0]
        cost = float(row.get("Cost", 0))
        revenue = float(row.get("Total Revenue", 0))  # Always use Total Revenue
        sales = float(row.get("Sales", 0))
        leads = float(row.get("Leads", 0))
        clicks = float(row.get("Click", 0))
        impressions = float(row.get("Impressions", 0))
        result[funnel] = {
            "source": _clean_source_name(row),
            "source_link": _clean_source_link(row),
            "cost": round(cost, 2),
            "revenue": round(revenue, 2),
            "sales": round(sales, 0),
            "leads": round(leads, 0),
            "clicks": round(clicks, 0),
            "impressions": round(impressions, 0),
            "roas": round(_safe_divide(revenue, cost), 2),
            "cps": round(_safe_divide(cost, sales), 2),
            "l2s_pct": round(_safe_divide(sales, leads) * 100, 2),
            "cvr_pct": round(_safe_divide(sales, clicks) * 100, 2),
        }
    return result

_BING_NAMES = {"bing", "microsoft", "microsoft ads", "bing ads"}
FUNNEL_STAGES = ("TOF", "MOF", "BOF")


def _detect_bing_label(df: pd.DataFrame) -> Optional[str]:
    """Return the exact Traffic Source label used for Bing/Microsoft, or None."""
    for val in df["Traffic Source"].dropna().unique():
        if str(val).strip().lower() in _BING_NAMES:
            return str(val).strip()
    return None


def calculate_total_funnel_distribution(platform_funnels: list[dict]) -> dict:
    """Calculate cross-platform spend/revenue distribution by funnel stage."""
    result = {}
    for stage in FUNNEL_STAGES:
        cost = round(sum(float(funnels.get(stage, {}).get("cost", 0) or 0) for funnels in platform_funnels), 2)
        revenue = round(sum(float(funnels.get(stage, {}).get("revenue", 0) or 0) for funnels in platform_funnels), 2)
        result[stage] = {"cost": cost, "revenue": revenue}

    total_cost = sum(stage["cost"] for stage in result.values())
    total_revenue = sum(stage["revenue"] for stage in result.values())
    for stage in FUNNEL_STAGES:
        result[stage]["cost_pct"] = round(_safe_divide(result[stage]["cost"], total_cost) * 100, 2)
        result[stage]["revenue_pct"] = round(_safe_divide(result[stage]["revenue"], total_revenue) * 100, 2)
    return result


def build_full_kpi_report(campaigns_df: pd.DataFrame, ads_df: pd.DataFrame) -> dict:
    """
    Build the complete KPI dict consumed by generate_insights and report replacement helpers.
    All revenue figures derive from the "Total Revenue" column.
    Bing is included when present; silently omitted when not in the data.
    """
    google = calculate_platform_kpis(campaigns_df, "google")
    meta   = calculate_platform_kpis(campaigns_df, "meta")

    bing_label = _detect_bing_label(campaigns_df)
    bing = calculate_platform_kpis(campaigns_df, bing_label) if bing_label else None

    all_platforms = [google, meta] + ([bing] if bing else [])
    total_cost    = round(sum(p["cost"]        for p in all_platforms), 2)
    total_revenue = round(sum(p["revenue"]     for p in all_platforms), 2)
    total_sales   = round(sum(p["sales"]       for p in all_platforms), 0)
    total_leads   = round(sum(p["leads"]       for p in all_platforms), 0)
    total_clicks  = round(sum(p["clicks"]      for p in all_platforms), 0)
    total_impr    = round(sum(p["impressions"] for p in all_platforms), 0)

    google_funnels = calculate_funnel_kpis(campaigns_df, "google")
    meta_funnels = calculate_funnel_kpis(campaigns_df, "meta")

    result = {
        "google":         google,
        "meta":           meta,
        "google_funnels": google_funnels,
        "meta_funnels":   meta_funnels,
        "google_funnel_cards": calculate_funnel_top_ads(ads_df, "google"),
        "meta_funnel_cards":   calculate_funnel_top_ads(ads_df, "meta"),
        "google_top_ads": calculate_top_ads(ads_df, "google"),
        "meta_top_ads":   calculate_top_ads(ads_df, "meta"),
        "meta_top_ads_detailed": calculate_detailed_top_meta_ads(ads_df),
        "top_ads_by_funnel_stage": calculate_top_ads_by_funnel_stage(ads_df),
        "totals": {
            "cost":        total_cost,
            "revenue":     total_revenue,
            "sales":       total_sales,
            "leads":       total_leads,
            "clicks":      total_clicks,
            "impressions": total_impr,
            "roas":    round(_safe_divide(total_revenue, total_cost), 2),
            "cps":     round(_safe_divide(total_cost, total_sales), 2),
            "l2s_pct": round(_safe_divide(total_sales, total_leads) * 100, 2),
            "cvr_pct": round(_safe_divide(total_sales, total_clicks) * 100, 2),
            "ctr_pct": round(_safe_divide(total_clicks, total_impr) * 100, 2),
            "aov":     round(_safe_divide(total_revenue, total_sales), 2),
        },
    }

    if bing:
        result["bing"]         = bing
        result["bing_funnels"] = calculate_funnel_kpis(campaigns_df, bing_label)
        result["bing_funnel_cards"] = calculate_funnel_top_ads(ads_df, bing_label)
        result["bing_top_ads"] = calculate_top_ads(ads_df, bing_label)

    platform_funnels = [google_funnels, meta_funnels]
    if result.get("bing_funnels"):
        platform_funnels.append(result["bing_funnels"])
    result["total_funnel_distribution"] = calculate_total_funnel_distribution(platform_funnels)

    return result
