import pandas as pd
from pathlib import Path
from typing import Union

REQUIRED_COLUMNS = [
    "Traffic Source", "Funnel", "Cost", "Total Revenue", "Sales",
    "Leads", "Click", "Impressions", "Average Order Value"
]

SUPPORTED_TRAFFIC_SOURCES = {
    "google": "google",
    "google v2": "google",
    "meta": "meta",
    "bing": "bing",
    "bing ads": "bing",
    "microsoft": "bing",
    "microsoft ads": "bing",
}


def canonicalize_traffic_sources(df: pd.DataFrame) -> pd.DataFrame:
    """Return a calculation copy with recognized source aliases canonicalized."""
    normalized = df.copy()
    if not hasattr(normalized, "columns") or "Traffic Source" not in normalized.columns:
        return normalized
    labels = normalized["Traffic Source"].astype(str).str.strip().str.lower()
    canonical = labels.map(SUPPORTED_TRAFFIC_SOURCES)
    normalized["Traffic Source"] = canonical.fillna(labels)
    return normalized

def load_sheet(path: Union[str, Path], sheet_name: str, client: str) -> pd.DataFrame:
    """
    Load a sheet from the Hyros xlsx export and filter by Client column.
    sheet_name is "Campaigns" or "Ads".
    """
    path = Path(path)
    df = pd.read_excel(path, sheet_name=sheet_name)
    # Normalize column names: strip whitespace
    df.columns = df.columns.str.strip()
    # Filter to the target client
    if "Client" in df.columns:
        df = df[df["Client"] == client].copy()
    for col in ["Cost", "Total Revenue", "Sales", "Leads", "Impressions", "Click", "Average Order Value"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df.reset_index(drop=True)


def run_checkpoints(df: pd.DataFrame) -> dict:
    """
    Run the mandatory verification checkpoints.
    Returns dict with checkpoint_N_passed keys and computed totals.
    """
    tol = 0.01  # $0.01 tolerance for floating point

    source_labels = df["Traffic Source"].astype(str).str.strip().str.lower()
    canonical_sources = source_labels.map(SUPPORTED_TRAFFIC_SOURCES)
    google = df[canonical_sources == "google"]
    meta   = df[canonical_sources == "meta"]
    bing   = df[canonical_sources == "bing"]
    supported = df[canonical_sources.notna()]
    unknown_sources = sorted(set(source_labels[canonical_sources.isna()]))

    google_cost  = google["Cost"].sum()
    meta_cost    = meta["Cost"].sum()
    bing_cost    = bing["Cost"].sum()
    supported_cost = supported["Cost"].sum()
    total_cost   = df["Cost"].sum()

    google_sales = google["Sales"].sum()
    meta_sales   = meta["Sales"].sum()
    bing_sales   = bing["Sales"].sum()
    supported_sales = supported["Sales"].sum()
    total_sales  = df["Sales"].sum()

    google_tof_sales = google[google["Funnel"].str.upper() == "TOF"]["Sales"].sum()
    google_mof_sales = google[google["Funnel"].str.upper() == "MOF"]["Sales"].sum()
    google_bof_sales = google[google["Funnel"].str.upper() == "BOF"]["Sales"].sum()

    meta_tof_sales = meta[meta["Funnel"].str.upper() == "TOF"]["Sales"].sum()
    meta_mof_sales = meta[meta["Funnel"].str.upper() == "MOF"]["Sales"].sum()
    meta_bof_sales = meta[meta["Funnel"].str.upper() == "BOF"]["Sales"].sum()

    bing_tof_sales = bing[bing["Funnel"].str.upper() == "TOF"]["Sales"].sum()
    bing_mof_sales = bing[bing["Funnel"].str.upper() == "MOF"]["Sales"].sum()
    bing_bof_sales = bing[bing["Funnel"].str.upper() == "BOF"]["Sales"].sum()

    cp1 = bool(not unknown_sources and abs(supported_cost - total_cost) < tol)
    cp2 = bool(not unknown_sources and abs(supported_sales - total_sales) < tol)
    cp3 = bool(abs((google_tof_sales + google_mof_sales + google_bof_sales) - google_sales) < tol)
    cp4 = bool(abs((meta_tof_sales + meta_mof_sales + meta_bof_sales) - meta_sales) < tol)
    cp5 = bool(abs((bing_tof_sales + bing_mof_sales + bing_bof_sales) - bing_sales) < tol)

    return {
        "checkpoint_1_passed": cp1,
        "checkpoint_2_passed": cp2,
        "checkpoint_3_passed": cp3,
        "checkpoint_4_passed": cp4,
        "checkpoint_5_bing_funnel_sales_passed": cp5,
        "unknown_traffic_sources": unknown_sources,
        "google_cost": google_cost, "meta_cost": meta_cost, "bing_cost": bing_cost,
        "supported_cost": supported_cost, "total_cost": total_cost,
        "google_sales": google_sales, "meta_sales": meta_sales, "bing_sales": bing_sales,
        "supported_sales": supported_sales, "total_sales": total_sales,
    }


def validate_or_raise(df: pd.DataFrame) -> dict:
    """Run checkpoints and raise ValueError if any fail."""
    results = run_checkpoints(df)
    failures = [k for k, v in results.items() if k.startswith("checkpoint") and not v]
    if failures:
        raise ValueError(f"Data validation FAILED: {failures}\nTotals: {results}")
    return results
