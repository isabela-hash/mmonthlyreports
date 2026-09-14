"""Build formatted placeholder values for monthly Google Slides reports."""
from __future__ import annotations

from typing import Any, Callable

FUNNEL_STAGES = ("TOF", "MOF", "BOF")
PLATFORM_TOKENS = {"google": "GOOGLE", "meta": "META", "bing": "BING"}
TABLE_PLACEHOLDER_TOKENS = {
    "{{META_TOP_10_ADS_TABLE}}",
    "{{TOP_3_FUNNEL_ADS_TABLE}}",
}

REQUIRED_TEMPLATE_TOKENS = {
    "{{CLIENT}}",
    "{{REPORT_MONTH}}",
    "{{SLIDE4_AD_REVENUE}}",
    "{{SLIDE4_AD_COST}}",
    "{{SLIDE4_ROAS}}",
    "{{SLIDE4_CPS}}",
    "{{SLIDE4_L2S}}",
    "{{SLIDE4_CVR}}",
    "{{SLIDE4_AOV}}",
    "{{COMPANY_REVENUE}}",
    "{{PCT_REV_FROM_ADS}}",
    "{{GOOGLE_REVENUE}}",
    "{{GOOGLE_COST}}",
    "{{GOOGLE_SALES}}",
    "{{GOOGLE_ROAS}}",
    "{{GOOGLE_CPS}}",
    "{{GOOGLE_CTR}}",
    "{{GOOGLE_CVR}}",
    "{{GOOGLE_L2S}}",
    "{{META_REVENUE}}",
    "{{META_COST}}",
    "{{META_SALES}}",
    "{{META_ROAS}}",
    "{{META_CPS}}",
    "{{META_CTR}}",
    "{{META_CVR}}",
    "{{META_L2S}}",
    "{{SLIDE3_GENERAL_INSIGHTS}}",
    "{{SLIDE3_BUDGET_ROAS}}",
    "{{SLIDE3_STRATEGY}}",
    "{{GOOGLE_TOP_PERFORMER}}",
    "{{GOOGLE_NEXT_STEPS}}",
    "{{META_TOP_PERFORMER}}",
    "{{META_NEXT_STEPS}}",
    "{{PM_NARRATIVE}}",
    "{{ACTION_ITEM_1}}",
    "{{ACTION_ITEM_2}}",
    "{{ACTION_ITEM_3}}",
    "{{ACTION_ITEM_4}}",
    "{{ACTION_ITEM_5}}",
} | TABLE_PLACEHOLDER_TOKENS


def currency_symbol(currency: str | None = None) -> str:
    normalized = str(currency or "USD").strip().upper()
    return "€" if normalized == "EUR" else "$"


def fmt_pct(value: float | int | None) -> str:
    return f"{float(value or 0):.2f}%"


def fmt_pct_whole(value: float | int | None) -> str:
    return f"{float(value or 0):.0f}%"


def fmt_pct_card(value: float | int | None) -> str:
    numeric = float(value or 0)
    return f"{numeric:.0f}%" if abs(numeric) >= 10 else f"{numeric:.1f}%"


def fmt_money(value: float | int | None, currency: str | None = None) -> str:
    return f"{currency_symbol(currency)}{float(value or 0):,.2f}"


def fmt_money_whole(value: float | int | None, currency: str | None = None) -> str:
    return f"{currency_symbol(currency)}{float(value or 0):,.0f}"


def fmt_money_compact(value: float | int | None, currency: str | None = None) -> str:
    numeric = float(value or 0)
    if abs(numeric) >= 1000:
        return f"{currency_symbol(currency)}{numeric / 1000:,.0f}K"
    return fmt_money_whole(numeric, currency)


def fmt_usd(value: float | int | None) -> str:
    return fmt_money(value, "USD")


def fmt_usd_whole(value: float | int | None) -> str:
    return fmt_money_whole(value, "USD")


def fmt_usd_compact(value: float | int | None) -> str:
    return fmt_money_compact(value, "USD")


def fmt_int(value: float | int | None) -> str:
    return f"{int(float(value or 0)):,}"


def fmt_roas(value: float | int | None) -> str:
    return f"{float(value or 0):.2f}"


def fmt_roas_card(value: float | int | None) -> str:
    numeric = float(value or 0)
    if abs(numeric) >= 10:
        return f"{numeric:.0f}"
    return f"{numeric:.1f}"


def fmt_number_compact(value: float | int | None, decimals: int = 1) -> str:
    numeric = float(value or 0)
    sign = "-" if numeric < 0 else ""
    numeric = abs(numeric)
    if numeric >= 1_000_000:
        return f"{sign}{numeric / 1_000_000:.{decimals}f}M"
    if numeric >= 1000:
        return f"{sign}{numeric / 1000:.{decimals}f}K"
    if numeric == int(numeric):
        return f"{sign}{int(numeric):,}"
    return f"{sign}{numeric:.{decimals}f}"


def _safe_value(data: dict[str, Any], key: str, formatter: Callable[[Any], str]) -> str:
    value = data.get(key)
    if value is None:
        return ""
    return formatter(value)


def _funnel_value(funnels: dict[str, Any], stage: str, key: str, formatter: Callable[[Any], str]) -> str:
    stage_data = funnels.get(stage)
    if not stage_data or key not in stage_data or stage_data.get(key) is None:
        return "N/A"
    return formatter(stage_data.get(key))


def _platform_replacements(
    prefix: str,
    data: dict[str, Any],
    previous: dict[str, Any] | None = None,
    currency: str | None = None,
) -> dict[str, str]:
    previous = previous or {}
    token = prefix.upper()
    return {
        f"{{{{{token}_ROAS}}}}": fmt_roas(data.get("roas", 0)) if data else "",
        f"{{{{{token}_CPS}}}}": fmt_money(data.get("cps", 0), currency) if data else "",
        f"{{{{{token}_L2S}}}}": fmt_pct(data.get("l2s_pct", 0)) if data else "",
        f"{{{{{token}_CVR}}}}": fmt_pct(data.get("cvr_pct", 0)) if data else "",
        f"{{{{{token}_CTR}}}}": fmt_pct(data.get("ctr_pct", 0)) if data else "",
        f"{{{{{token}_REVENUE}}}}": fmt_money(data.get("revenue", 0), currency) if data else "",
        f"{{{{{token}_COST}}}}": fmt_money(data.get("cost", 0), currency) if data else "",
        f"{{{{{token}_SALES}}}}": fmt_int(data.get("sales", 0)) if data else "",
        f"{{{{{token}_CLICKS}}}}": fmt_int(data.get("clicks", 0)) if data else "",
        f"{{{{{token}_IMPRESSIONS}}}}": fmt_int(data.get("impressions", 0)) if data else "",
        f"{{{{{token}_LEADS}}}}": fmt_int(data.get("leads", 0)) if data else "",
        f"{{{{{token}_ROAS_PREV}}}}": _safe_value(previous, "roas", fmt_roas),
        f"{{{{{token}_CPS_PREV}}}}": _safe_value(previous, "cps", lambda v: fmt_money(v, currency)),
        f"{{{{{token}_L2S_PREV}}}}": _safe_value(previous, "l2s_pct", fmt_pct),
        f"{{{{{token}_CVR_PREV}}}}": _safe_value(previous, "cvr_pct", fmt_pct),
        f"{{{{{token}_CTR_PREV}}}}": _safe_value(previous, "ctr_pct", fmt_pct),
    }


def _funnel_replacements(prefix: str, funnels: dict[str, Any]) -> dict[str, str]:
    token = prefix.upper()
    replacements: dict[str, str] = {}
    for stage in ("TOF", "MOF", "BOF"):
        replacements.update(
            {
                f"{{{{{token}_{stage}_REVENUE}}}}": _funnel_value(funnels, stage, "revenue", fmt_usd),
                f"{{{{{token}_{stage}_COST}}}}": _funnel_value(funnels, stage, "cost", fmt_usd),
                f"{{{{{token}_{stage}_ROAS}}}}": _funnel_value(funnels, stage, "roas", fmt_roas),
                f"{{{{{token}_{stage}_SALES}}}}": _funnel_value(funnels, stage, "sales", fmt_int),
                f"{{{{{token}_{stage}_CPS}}}}": _funnel_value(funnels, stage, "cps", fmt_usd),
                f"{{{{{token}_{stage}_CR}}}}": _funnel_value(funnels, stage, "cvr_pct", fmt_pct),
            }
        )
    return replacements


def _funnel_card_replacements(prefix: str, funnels: dict[str, Any], currency: str | None = None) -> dict[str, str]:
    token = prefix.upper()
    replacements: dict[str, str] = {}
    for stage in ("TOF", "MOF", "BOF"):
        replacements.update(
            {
                f"{{{{{token}_{stage}_REVENUE}}}}": _funnel_value(funnels, stage, "revenue", lambda v: fmt_money_compact(v, currency)),
                f"{{{{{token}_{stage}_COST}}}}": _funnel_value(funnels, stage, "cost", lambda v: fmt_money_whole(v, currency)),
                f"{{{{{token}_{stage}_ROAS}}}}": _funnel_value(funnels, stage, "roas", fmt_roas_card),
                f"{{{{{token}_{stage}_SALES}}}}": _funnel_value(funnels, stage, "sales", fmt_int),
                f"{{{{{token}_{stage}_CPS}}}}": _funnel_value(funnels, stage, "cps", lambda v: fmt_money_whole(v, currency)),
                f"{{{{{token}_{stage}_CR}}}}": _funnel_value(funnels, stage, "cvr_pct", fmt_pct_card),
            }
        )
    return replacements


def _distribution_replacements(distribution: dict[str, Any], currency: str | None = None) -> dict[str, str]:
    replacements: dict[str, str] = {}
    for stage in FUNNEL_STAGES:
        stage_data = distribution.get(stage, {})
        replacements.update(
            {
                f"{{{{TOTAL_{stage}_COST}}}}": fmt_money_compact(stage_data.get("cost", 0), currency),
                f"{{{{TOTAL_{stage}_COST_PCT}}}}": fmt_pct_whole(stage_data.get("cost_pct", 0)),
                f"{{{{TOTAL_{stage}_REVENUE}}}}": fmt_money_compact(stage_data.get("revenue", 0), currency),
                f"{{{{TOTAL_{stage}_REVENUE_PCT}}}}": fmt_pct_whole(stage_data.get("revenue_pct", 0)),
            }
        )
    return replacements


def format_ad_name_with_source_link(card: dict[str, Any] | None) -> str:
    card = card or {}
    source = str(card.get("source") or "").strip()
    source_link = str(card.get("source_link") or "").strip()
    if not source and not source_link:
        return "N/A"
    if not source or source == "N/A":
        return source_link
    if source_link and source_link.lower() != source.lower():
        return f"{source} | Source Link: {source_link}"
    return source


def _ad_name_replacements(prefix: str, cards: dict[str, Any]) -> dict[str, str]:
    token = prefix.upper()
    return {
        f"{{{{{token}_{stage}_AD_NAME}}}}": format_ad_name_with_source_link(cards.get(stage, {}))
        for stage in FUNNEL_STAGES
    }


def _stage_distribution(stage: str, platform_funnels: dict[str, Any], platform_total: dict[str, Any]) -> str:
    stage_data = platform_funnels.get(stage, {})
    cost_pct = fmt_pct(stage_data.get("cost", 0) / platform_total.get("cost", 0) * 100) if platform_total.get("cost") else "0.00%"
    revenue_pct = (
        fmt_pct(stage_data.get("revenue", 0) / platform_total.get("revenue", 0) * 100)
        if platform_total.get("revenue")
        else "0.00%"
    )
    sales_pct = fmt_pct(stage_data.get("sales", 0) / platform_total.get("sales", 0) * 100) if platform_total.get("sales") else "0.00%"
    return f"{cost_pct} ad spend, {revenue_pct} ad revenue, and {sales_pct} of sales"


def build_funnel_narrative(
    platform_name: str,
    stage: str,
    platform_total: dict[str, Any],
    funnel_data: dict[str, Any],
    top_ad: dict[str, Any] | None = None,
    currency: str | None = None,
    next_steps: str | None = None,
) -> str:
    top_ad = top_ad or {}
    if not funnel_data:
        return f"No {stage} data was available for {platform_name} this month."

    cps = "No data CPS" if not funnel_data.get("sales") else f"{fmt_money_compact(funnel_data.get('cps', 0), currency)} CPS"
    headline = (
        f"{fmt_number_compact(funnel_data.get('impressions', 0))} Impressions | "
        f"{fmt_number_compact(funnel_data.get('clicks', 0))} Clicks | "
        f"{fmt_number_compact(funnel_data.get('leads', 0))} Leads | "
        f"{fmt_int(funnel_data.get('sales', 0))} Sales | "
        f"{fmt_money_compact(funnel_data.get('revenue', 0), currency)} Ad Revenue | "
        f"{fmt_money_compact(funnel_data.get('cost', 0), currency)} Ad Spend | "
        f"{cps} | {fmt_roas_card(funnel_data.get('roas', 0))} ROAS"
    )
    distribution = f"Distribution: {_stage_distribution(stage, {stage: funnel_data}, platform_total)}."
    if top_ad:
        contribution = (
            top_ad.get("revenue", 0) / funnel_data.get("revenue", 0) * 100
            if funnel_data.get("revenue")
            else 0
        )
        performer = (
            f"Top Performer: {top_ad.get('source', 'N/A')} reached a {fmt_roas_card(top_ad.get('roas', 0))} ROAS, "
            f"{fmt_int(top_ad.get('sales', 0))} sales and {fmt_money_whole(top_ad.get('revenue', 0), currency)} revenue, "
            f"which is around {fmt_pct_whole(contribution)} of funnel stage revenue."
        )
    else:
        performer = "Top Performer: No positive-revenue ad was available for this funnel stage."
    action = next_steps or f"Next Steps: Review {platform_name} {stage} performance and refine budget, targeting, and creative based on this stage's efficiency."
    return "\n".join([headline, distribution, performer, action])


def build_deterministic_funnel_narratives(kpis: dict, currency: str | None = None) -> dict[str, str]:
    narratives: dict[str, str] = {}
    for platform_key, token_prefix in PLATFORM_TOKENS.items():
        platform_total = kpis.get(platform_key, {})
        funnels = kpis.get(f"{platform_key}_funnels", {})
        top_ads = kpis.get(f"{platform_key}_funnel_cards", {})
        for stage in FUNNEL_STAGES:
            narratives[f"{platform_key}_{stage.lower()}_narrative"] = build_funnel_narrative(
                token_prefix.title() if token_prefix != "GOOGLE" else "Google",
                stage,
                platform_total,
                funnels.get(stage, {}),
                top_ads.get(stage, {}),
                currency,
            )
    return narratives


def _extract_funnel_next_steps(ai_narrative: Any) -> str | None:
    """Keep AI strategy while rejecting AI-generated metric lines."""
    for line in str(ai_narrative or "").splitlines():
        normalized = line.strip()
        if normalized.lower().startswith("next steps:"):
            return normalized
    return None


def build_audit_replacements(
    client: str,
    month: str,
    year: int,
    prev_month: str,
    next_month: str,
) -> dict[str, str]:
    """Build a complete sample replacement map for template-only audits."""
    platform_sample = {
        "revenue": 1000,
        "cost": 500,
        "sales": 10,
        "leads": 50,
        "clicks": 250,
        "impressions": 10000,
        "roas": 2,
        "cps": 50,
        "l2s_pct": 20,
        "cvr_pct": 4,
        "ctr_pct": 2.5,
    }
    funnel_sample = {
        stage: {
            "revenue": 1000,
            "cost": 500,
            "sales": 10,
            "leads": 50,
            "clicks": 250,
            "impressions": 10000,
            "cps": 50,
            "roas": 2,
            "cvr_pct": 4,
            "source": f"Sample {stage} ad",
        }
        for stage in ("TOF", "MOF", "BOF")
    }
    kpis = {
        "google": dict(platform_sample),
        "meta": dict(platform_sample),
        "bing": dict(platform_sample),
        "google_funnels": dict(funnel_sample),
        "meta_funnels": dict(funnel_sample),
        "bing_funnels": dict(funnel_sample),
        "google_funnel_cards": dict(funnel_sample),
        "meta_funnel_cards": dict(funnel_sample),
        "bing_funnel_cards": dict(funnel_sample),
        "total_funnel_distribution": {
            stage: {"cost": 500, "cost_pct": 33.33, "revenue": 1000, "revenue_pct": 33.33}
            for stage in ("TOF", "MOF", "BOF")
        },
        "totals": {
            "revenue": 3000,
            "cost": 1500,
            "sales": 30,
            "roas": 2,
            "cps": 50,
            "l2s_pct": 20,
            "cvr_pct": 4,
            "aov": 100,
        },
    }
    insights = {
        "slide3_general_insights": "Sample general insights.",
        "slide3_budget_roas": "Sample budget and ROAS note.",
        "slide3_strategy": "Sample strategy note.",
        "google_top_performer": "Sample Google top performer.",
        "google_main_drop": "Sample Google main drop.",
        "google_next_steps": "Sample Google next steps.",
        "meta_top_performer": "Sample Meta top performer.",
        "meta_main_drop": "Sample Meta main drop.",
        "meta_next_steps": "Sample Meta next steps.",
        "performance_manager_narrative": "Sample performance manager narrative.",
        **build_deterministic_funnel_narratives(kpis),
        "action_items": [
            "Sample action item 1.",
            "Sample action item 2.",
            "Sample action item 3.",
            "Sample action item 4.",
            "Sample action item 5.",
        ],
    }
    overrides = {
        "company_revenue": 5000,
        "ad_revenue": 3000,
        "ad_cost": 1500,
        "prev_company_revenue": 4000,
        "prev_ad_revenue": 2400,
        "prev_ad_cost": 1200,
    }
    return build_replacements(
        client,
        month,
        year,
        prev_month,
        next_month,
        kpis,
        insights,
        overrides,
        prev_kpis=kpis,
    )


def build_replacements(
    client: str,
    month: str,
    year: int,
    prev_month: str,
    next_month: str,
    kpis: dict,
    insights: dict,
    user_overrides: dict,
    prev_kpis: dict | None = None,
) -> dict[str, str]:
    """Build the full placeholder-to-value map for Google Slides reports."""
    totals = kpis["totals"]
    currency = str(user_overrides.get("currency", "USD") or "USD").upper()
    prev_totals = prev_kpis.get("totals", {}) if prev_kpis else {}
    ad_revenue = user_overrides.get("ad_revenue") or totals["revenue"]
    ad_cost = user_overrides.get("ad_cost") or totals["cost"]
    company_revenue = 0

    slide4_roas = fmt_roas(ad_revenue / ad_cost) if ad_cost else fmt_roas(totals.get("roas", 0))
    slide4_cps = fmt_money(ad_cost / totals["sales"], currency) if totals.get("sales") else fmt_money(0, currency)
    pct_rev = "0%"

    p_company_revenue = 0
    p_ad_revenue = user_overrides.get("prev_ad_revenue") or prev_totals.get("revenue", 0)
    p_ad_cost = user_overrides.get("prev_ad_cost") or prev_totals.get("cost", 0)
    p_sales = prev_totals.get("sales", 0)
    p_slide4_roas = fmt_roas(p_ad_revenue / p_ad_cost) if prev_kpis and p_ad_cost else ""
    p_slide4_cps = fmt_money(p_ad_cost / p_sales, currency) if prev_kpis and p_sales else ""
    p_pct_rev = "0%" if prev_kpis else ""
    action_items = insights.get("action_items", [])

    replacements = {
        "{{META_TOP_10_ADS_TABLE}}": "{{META_TOP_10_ADS_TABLE}}",
        "{{TOP_3_FUNNEL_ADS_TABLE}}": "{{TOP_3_FUNNEL_ADS_TABLE}}",
        "{{MONTH}}": month,
        "{{YEAR}}": str(year),
        "{{REPORT_MONTH}}": f"{month} {year}",
        "{{MONTH_YEAR}}": f"{month} {year}",
        "{{CLIENT}}": client,
        "{{PREV_MONTH}}": prev_month,
        "{{NEXT_MONTH}}": next_month,
        "{{SLIDE4_AD_REVENUE}}": fmt_money(ad_revenue, currency),
        "{{SLIDE4_AD_COST}}": fmt_money(ad_cost, currency),
        "{{SLIDE4_ROAS}}": slide4_roas,
        "{{SLIDE4_CPS}}": slide4_cps,
        "{{SLIDE4_L2S}}": fmt_pct(totals.get("l2s_pct", 0)),
        "{{SLIDE4_CVR}}": fmt_pct(totals.get("cvr_pct", 0)),
        "{{SLIDE4_AOV}}": fmt_money(totals.get("aov", 0), currency),
        "{{COMPANY_REVENUE}}": fmt_money(company_revenue, currency),
        "{{PCT_REV_FROM_ADS}}": pct_rev,
        "{{SLIDE4_AD_REVENUE_PREV}}": fmt_money(p_ad_revenue, currency) if prev_kpis else "",
        "{{SLIDE4_AD_COST_PREV}}": fmt_money(p_ad_cost, currency) if prev_kpis else "",
        "{{SLIDE4_ROAS_PREV}}": p_slide4_roas,
        "{{SLIDE4_CPS_PREV}}": p_slide4_cps,
        "{{SLIDE4_L2S_PREV}}": fmt_pct(prev_totals.get("l2s_pct", 0)) if prev_kpis else "",
        "{{SLIDE4_CVR_PREV}}": fmt_pct(prev_totals.get("cvr_pct", 0)) if prev_kpis else "",
        "{{SLIDE4_AOV_PREV}}": fmt_money(prev_totals.get("aov", 0), currency) if prev_kpis else "",
        "{{COMPANY_REVENUE_PREV}}": fmt_money(p_company_revenue, currency) if prev_kpis else "",
        "{{PCT_REV_FROM_ADS_PREV}}": p_pct_rev,
        "{{SLIDE3_GENERAL_INSIGHTS}}": insights.get("slide3_general_insights", ""),
        "{{SLIDE3_BUDGET_ROAS}}": insights.get("slide3_budget_roas", ""),
        "{{SLIDE3_STRATEGY}}": insights.get("slide3_strategy", ""),
        "{{GOOGLE_TOP_PERFORMER}}": insights.get("google_top_performer", ""),
        "{{GOOGLE_MAIN_DROP}}": insights.get("google_main_drop", ""),
        "{{GOOGLE_NEXT_STEPS}}": insights.get("google_next_steps", ""),
        "{{META_TOP_PERFORMER}}": insights.get("meta_top_performer", ""),
        "{{META_MAIN_DROP}}": insights.get("meta_main_drop", ""),
        "{{META_NEXT_STEPS}}": insights.get("meta_next_steps", ""),
        "{{PM_NARRATIVE}}": insights.get("performance_manager_narrative", ""),
    }

    for platform_key, token_prefix in PLATFORM_TOKENS.items():
        platform_total = kpis.get(platform_key, {})
        funnels = kpis.get(f"{platform_key}_funnels", {})
        top_ads = kpis.get(f"{platform_key}_funnel_cards", {})
        platform_name = token_prefix.title() if token_prefix != "GOOGLE" else "Google"
        for stage in FUNNEL_STAGES:
            insight_key = f"{platform_key}_{stage.lower()}_narrative"
            replacements[f"{{{{{token_prefix}_{stage}_NARRATIVE}}}}"] = build_funnel_narrative(
                platform_name,
                stage,
                platform_total,
                funnels.get(stage, {}),
                top_ads.get(stage, {}),
                currency,
                next_steps=_extract_funnel_next_steps(insights.get(insight_key, "")),
            )

    for index in range(5):
        replacements[f"{{{{ACTION_ITEM_{index + 1}}}}}"] = action_items[index] if len(action_items) > index else ""

    replacements.update(_platform_replacements("google", kpis["google"], prev_kpis.get("google", {}) if prev_kpis else None, currency))
    replacements.update(_platform_replacements("meta", kpis["meta"], prev_kpis.get("meta", {}) if prev_kpis else None, currency))
    replacements.update(_platform_replacements("bing", kpis.get("bing", {}), prev_kpis.get("bing", {}) if prev_kpis else None, currency))
    replacements.update(_funnel_card_replacements("google", kpis.get("google_funnel_cards", kpis.get("google_funnels", {})), currency))
    replacements.update(_funnel_card_replacements("meta", kpis.get("meta_funnel_cards", kpis.get("meta_funnels", {})), currency))
    replacements.update(_funnel_card_replacements("bing", kpis.get("bing_funnel_cards", kpis.get("bing_funnels", {})), currency))
    replacements.update(_ad_name_replacements("google", kpis.get("google_funnel_cards", {})))
    replacements.update(_ad_name_replacements("meta", kpis.get("meta_funnel_cards", {})))
    replacements.update(_ad_name_replacements("bing", kpis.get("bing_funnel_cards", {})))
    replacements.update(_distribution_replacements(kpis.get("total_funnel_distribution", {}), currency))

    return {key: "" if value is None else str(value) for key, value in replacements.items()}
