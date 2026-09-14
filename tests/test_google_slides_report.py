import inspect

import tools.google_slides_report as google_slides_report
from tools.google_slides_report import (
    audit_placeholders,
    build_funnel_stage_table_rows,
    build_meta_top_ads_table_rows,
    build_slides_replacements,
    extract_placeholders_from_presentation,
    find_sheets_chart_object_ids,
    make_replace_all_text_requests,
)
from tools.report_replacements import REQUIRED_TEMPLATE_TOKENS, build_audit_replacements


def test_extract_placeholders_from_shapes_and_tables():
    presentation = {
        "slides": [
            {
                "pageElements": [
                    {
                        "shape": {
                            "text": {
                                "textElements": [
                                    {"textRun": {"content": "{{CLIENT}}\n"}},
                                    {"textRun": {"content": "Revenue {{GOOGLE_REVENUE}}"}},
                                ]
                            }
                        }
                    },
                    {
                        "table": {
                            "tableRows": [
                                {
                                    "tableCells": [
                                        {
                                            "text": {
                                                "textElements": [
                                                    {"textRun": {"content": "{{META_ROAS}}"}}
                                                ]
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    },
                ]
            }
        ]
    }

    found = extract_placeholders_from_presentation(presentation)

    assert found == {"{{CLIENT}}", "{{GOOGLE_REVENUE}}", "{{META_ROAS}}"}


def test_make_replace_all_text_requests_uses_exact_case_sensitive_tokens():
    requests = make_replace_all_text_requests({"{{CLIENT}}": "One Funded"})

    assert requests == [
        {
            "replaceAllText": {
                "containsText": {"text": "{{CLIENT}}", "matchCase": True},
                "replaceText": "One Funded",
            }
        }
    ]


def test_make_replace_all_text_requests_skips_table_placeholders():
    requests = make_replace_all_text_requests(
        {
            "{{CLIENT}}": "One Funded",
            "{{META_TOP_10_ADS_TABLE}}": "{{META_TOP_10_ADS_TABLE}}",
            "{{TOP_3_FUNNEL_ADS_TABLE}}": "{{TOP_3_FUNNEL_ADS_TABLE}}",
        }
    )

    assert requests == [
        {
            "replaceAllText": {
                "containsText": {"text": "{{CLIENT}}", "matchCase": True},
                "replaceText": "One Funded",
            }
        }
    ]


def test_audit_placeholders_reports_missing_and_unused_values():
    audit = audit_placeholders(
        {"{{CLIENT}}", "{{MISSING}}"},
        {"{{CLIENT}}", "{{UNUSED}}"},
    )

    assert audit["missing_values"] == ["{{MISSING}}"]
    assert audit["unused_values"] == ["{{UNUSED}}"]


def test_find_sheets_chart_object_ids():
    presentation = {
        "slides": [
            {
                "pageElements": [
                    {"objectId": "chart_1", "sheetsChart": {"chartId": 123}},
                    {"objectId": "shape_1", "shape": {}},
                ]
            }
        ]
    }

    assert find_sheets_chart_object_ids(presentation) == ["chart_1"]


def test_google_slides_report_uses_report_replacements_not_pptx_module():
    source = inspect.getsource(google_slides_report)

    assert "tools.report_replacements" in source
    assert "fill_pptx" not in source


def test_build_slides_replacements_contains_required_template_tokens():
    kpis = {
        "google": {
            "revenue": 1000,
            "cost": 500,
            "sales": 10,
            "leads": 50,
            "clicks": 200,
            "impressions": 10000,
            "roas": 2,
            "cps": 50,
            "l2s_pct": 20,
            "cvr_pct": 5,
            "ctr_pct": 2,
        },
        "meta": {
            "revenue": 800,
            "cost": 400,
            "sales": 8,
            "leads": 40,
            "clicks": 160,
            "impressions": 8000,
            "roas": 2,
            "cps": 50,
            "l2s_pct": 20,
            "cvr_pct": 5,
            "ctr_pct": 2,
        },
        "bing": {
            "revenue": 300,
            "cost": 150,
            "sales": 3,
            "leads": 15,
            "clicks": 60,
            "impressions": 3000,
            "roas": 2,
            "cps": 50,
            "l2s_pct": 20,
            "cvr_pct": 5,
            "ctr_pct": 2,
        },
        "google_funnels": {"TOF": {"revenue": 100, "cost": 50, "sales": 1, "cps": 50, "roas": 2, "cvr_pct": 1}},
        "meta_funnels": {"MOF": {"revenue": 200, "cost": 100, "sales": 2, "cps": 50, "roas": 2, "cvr_pct": 2}},
        "bing_funnels": {"BOF": {"revenue": 300, "cost": 150, "sales": 3, "cps": 50, "roas": 2, "cvr_pct": 3}},
        "google_funnel_cards": {
            "TOF": {"source": "Google TOF Winner", "source_link": "TOF - Branded - Exact - US", "revenue": 1044.40, "cost": 53.99, "sales": 3, "cps": 18, "roas": 19.34, "cvr_pct": 27.27}
        },
        "meta_funnel_cards": {
            "MOF": {"source": "Meta MOF Winner", "source_link": "MOF - Website Visitors", "revenue": 390.45, "cost": 44.25, "sales": 7, "cps": 6.32, "roas": 8.82, "cvr_pct": 3.43}
        },
        "bing_funnel_cards": {
            "BOF": {"source": "Bing BOF Winner", "source_link": "BOF - Branded - Bing", "revenue": 300, "cost": 150, "sales": 3, "cps": 50, "roas": 2, "cvr_pct": 3}
        },
        "total_funnel_distribution": {
            "TOF": {"cost": 50, "cost_pct": 16.67, "revenue": 100, "revenue_pct": 16.67},
            "MOF": {"cost": 100, "cost_pct": 33.33, "revenue": 200, "revenue_pct": 33.33},
            "BOF": {"cost": 150, "cost_pct": 50, "revenue": 300, "revenue_pct": 50},
        },
        "totals": {
            "revenue": 2100,
            "cost": 1050,
            "sales": 21,
            "roas": 2,
            "cps": 50,
            "l2s_pct": 20,
            "cvr_pct": 5,
            "aov": 100,
        },
    }
    insights = {
        "slide3_general_insights": "General",
        "slide3_budget_roas": "Budget",
        "slide3_strategy": "Strategy",
        "google_top_performer": "Google top",
        "google_main_drop": "Google drop",
        "google_next_steps": "Google next",
        "meta_top_performer": "Meta top",
        "meta_main_drop": "Meta drop",
        "meta_next_steps": "Meta next",
        "performance_manager_narrative": "PM",
        "action_items": ["A1", "A2", "A3", "A4", "A5"],
    }

    replacements = build_slides_replacements(
        "One Funded",
        "March",
        2026,
        "February",
        "April",
        kpis,
        insights,
        {"company_revenue": 3000},
    )

    assert REQUIRED_TEMPLATE_TOKENS <= set(replacements)
    assert replacements["{{REPORT_MONTH}}"] == "March 2026"
    assert replacements["{{CLIENT}}"] == "One Funded"
    assert replacements["{{ACTION_ITEM_5}}"] == "A5"
    assert replacements["{{COMPANY_REVENUE}}"] == "$0.00"
    assert replacements["{{PCT_REV_FROM_ADS}}"] == "0%"
    assert replacements["{{GOOGLE_TOF_REVENUE}}"] == "$1K"
    assert replacements["{{GOOGLE_TOF_ROAS}}"] == "19"
    assert replacements["{{GOOGLE_TOF_CPS}}"] == "$18"
    assert replacements["{{GOOGLE_TOF_CR}}"] == "27%"
    assert replacements["{{GOOGLE_BOF_REVENUE}}"] == "N/A"
    assert replacements["{{META_MOF_SALES}}"] == "7"
    assert replacements["{{META_MOF_REVENUE}}"] == "$390"
    assert replacements["{{META_MOF_CR}}"] == "3.4%"
    assert replacements["{{META_BOF_REVENUE}}"] == "N/A"
    assert replacements["{{BING_BOF_ROAS}}"] == "2.0"
    assert replacements["{{TOTAL_TOF_COST}}"] == "$50"
    assert replacements["{{TOTAL_BOF_REVENUE_PCT}}"] == "50%"
    assert replacements["{{GOOGLE_TOF_AD_NAME}}"] == "Google TOF Winner | Source Link: TOF - Branded - Exact - US"
    assert replacements["{{META_MOF_AD_NAME}}"] == "Meta MOF Winner | Source Link: MOF - Website Visitors"
    assert replacements["{{BING_BOF_AD_NAME}}"] == "Bing BOF Winner | Source Link: BOF - Branded - Bing"
    assert "Impressions |" in replacements["{{GOOGLE_TOF_NARRATIVE}}"]
    assert replacements["{{META_TOP_10_ADS_TABLE}}"] == "{{META_TOP_10_ADS_TABLE}}"
    assert replacements["{{TOP_3_FUNNEL_ADS_TABLE}}"] == "{{TOP_3_FUNNEL_ADS_TABLE}}"

    eur_replacements = build_slides_replacements(
        "One Funded",
        "March",
        2026,
        "February",
        "April",
        kpis,
        insights,
        {"company_revenue": 3000, "currency": "EUR"},
    )
    assert eur_replacements["{{GOOGLE_TOF_REVENUE}}"] == "€1K"
    assert eur_replacements["{{SLIDE4_AD_COST}}"].startswith("€")


def test_funnel_narrative_uses_aggregate_metrics_not_ai_top_ad_metrics():
    kpis = {
        "google": {"cost": 137635.21, "revenue": 307275.14, "sales": 820},
        "meta": {},
        "google_funnels": {
            "TOF": {
                "impressions": 42413,
                "clicks": 1917,
                "leads": 220,
                "sales": 84,
                "revenue": 24710.59,
                "cost": 14505.60,
                "cps": 172.69,
                "roas": 1.70,
            }
        },
        "meta_funnels": {},
        "google_funnel_cards": {
            "TOF": {
                "source": "Top Google TOF ad",
                "impressions": 2854,
                "clicks": 150,
                "leads": 4,
                "sales": 19,
                "revenue": 7440.45,
                "cost": 1073.63,
                "roas": 6.93,
            }
        },
        "meta_funnel_cards": {},
        "total_funnel_distribution": {},
        "totals": {
            "revenue": 307275.14,
            "cost": 137635.21,
            "sales": 820,
            "roas": 2.23,
            "cps": 167.85,
            "l2s_pct": 33.01,
            "cvr_pct": 1.15,
            "aov": 374.73,
        },
    }
    misleading_ai_narrative = (
        "2,854 Impressions | 150 Clicks | 4 Leads | 19 Sales | $7,440.45 Ad Revenue\n"
        "Distribution: 7.4% of Google TOF ad spend.\n"
        "Top Performer: Top Google TOF ad reached a 6.93 ROAS.\n"
        "Next Steps: Keep the winning ad controlled while validating attribution."
    )

    replacements = build_slides_replacements(
        "Alpha Funded",
        "August",
        2026,
        "July",
        "September",
        kpis,
        {
            "google_tof_narrative": misleading_ai_narrative,
            "action_items": [],
        },
        {},
    )

    narrative = replacements["{{GOOGLE_TOF_NARRATIVE}}"]
    assert "42.4K Impressions | 1.9K Clicks | 220 Leads | 84 Sales" in narrative
    assert "$25K Ad Revenue | $15K Ad Spend | $173 CPS | 1.7 ROAS" in narrative
    assert "Distribution: 10.54% ad spend, 8.04% ad revenue, and 10.24% of sales." in narrative
    assert "2,854 Impressions" not in narrative
    assert narrative.endswith("Next Steps: Keep the winning ad controlled while validating attribution.")


def test_build_audit_replacements_contains_dynamic_template_tokens():
    replacements = build_audit_replacements("One Funded", "March", 2026, "February", "April")

    expected_tokens = REQUIRED_TEMPLATE_TOKENS | {
        "{{BING_REVENUE}}",
        "{{BING_COST}}",
        "{{BING_SALES}}",
        "{{GOOGLE_TOF_REVENUE}}",
        "{{GOOGLE_MOF_SALES}}",
        "{{GOOGLE_BOF_ROAS}}",
        "{{META_TOF_CPS}}",
        "{{META_MOF_CR}}",
        "{{META_BOF_SALES}}",
        "{{BING_TOF_REVENUE}}",
        "{{BING_MOF_SALES}}",
        "{{BING_BOF_ROAS}}",
        "{{SLIDE4_AD_REVENUE_PREV}}",
        "{{GOOGLE_ROAS_PREV}}",
        "{{META_CPS_PREV}}",
        "{{BING_CVR_PREV}}",
        "{{GOOGLE_TOF_NARRATIVE}}",
        "{{META_MOF_NARRATIVE}}",
        "{{BING_BOF_NARRATIVE}}",
        "{{TOTAL_TOF_COST}}",
        "{{TOTAL_MOF_COST_PCT}}",
        "{{TOTAL_BOF_REVENUE}}",
        "{{GOOGLE_TOF_AD_NAME}}",
        "{{META_MOF_AD_NAME}}",
        "{{BING_BOF_AD_NAME}}",
        "{{META_TOP_10_ADS_TABLE}}",
        "{{TOP_3_FUNNEL_ADS_TABLE}}",
    }

    assert expected_tokens <= set(replacements)
    assert replacements["{{REPORT_MONTH}}"] == "March 2026"
    assert replacements["{{CLIENT}}"] == "One Funded"


def test_build_meta_top_ads_table_rows_formats_expected_columns():
    rows = build_meta_top_ads_table_rows(
        {
            "meta_top_ads_detailed": [
                {
                    "source": "Video - This is intentionally included in top Meta Ads",
                    "cost": 12.34,
                    "revenue": 123.45,
                    "revenue_pct": 67.89,
                    "sales": 3,
                    "clicks": 45,
                    "roas": 10,
                    "cps": 4.11,
                    "cvr_pct": 6.67,
                    "leads": 9,
                    "ctr_pct": 1.23,
                }
            ]
        }
    )

    assert rows[0] == ["Ad Name", "Ad Spend", "Ad Revenue", "% of Ad Revenue", "Sales", "Clicks", "ROAS", "CPS", "CR", "Leads", "CTR"]
    assert rows[1][0].startswith("Video - This is intentionally")
    assert rows[1][1:] == ["$12", "$123", "67.9%", "3", "45", "10.00", "$4", "6.7%", "9", "1.2%"]
    assert len(rows) == 11


def test_build_funnel_stage_table_rows_formats_top_three():
    rows = build_funnel_stage_table_rows(
        {
            "top_ads_by_funnel_stage": {
                "TOF": [
                    {"traffic_source": "google", "source": "Google TOF Winner", "revenue": 300, "roas": 3, "sales": 10, "cps": 30},
                    {"traffic_source": "meta", "source": "Meta TOF Runner", "revenue": 200, "roas": 2, "sales": 5, "cps": 40},
                ]
            }
        },
        "TOF",
    )

    assert rows[0] == ["Rank", "Channel", "Ad Name", "Revenue", "ROAS", "Sales", "CPS"]
    assert rows[1] == ["1", "google", "Google TOF Winner", "$300", "3.00", "10", "$30"]
    assert rows[2] == ["2", "meta", "Meta TOF Runner", "$200", "2.00", "5", "$40"]
    assert rows[3][1] == "N/A"


def test_ad_name_placeholder_uses_source_link_when_ad_name_is_missing():
    replacements = build_slides_replacements(
        "One Funded",
        "March",
        2026,
        "February",
        "April",
        {
            "google": {},
            "meta": {},
            "google_funnels": {},
            "meta_funnels": {},
            "google_funnel_cards": {"TOF": {"source": "N/A", "source_link": "TOF - Campaign Name"}},
            "meta_funnel_cards": {},
            "total_funnel_distribution": {},
            "totals": {"revenue": 0, "cost": 0, "sales": 0, "roas": 0, "cps": 0, "l2s_pct": 0, "cvr_pct": 0, "aov": 0},
        },
        {},
        {},
    )

    assert replacements["{{GOOGLE_TOF_AD_NAME}}"] == "TOF - Campaign Name"


def test_build_slides_replacements_uses_previous_kpis_and_overrides():
    kpis = {
        "google": {"roas": 2, "cps": 50, "l2s_pct": 20, "cvr_pct": 5, "ctr_pct": 2},
        "meta": {"roas": 1, "cps": 100, "l2s_pct": 10, "cvr_pct": 1, "ctr_pct": 1},
        "bing": {"roas": 3, "cps": 25, "l2s_pct": 30, "cvr_pct": 6, "ctr_pct": 3},
        "google_funnels": {},
        "meta_funnels": {},
        "bing_funnels": {},
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
    prev_kpis = {
        "google": {"roas": 1.5, "cps": 40, "l2s_pct": 18, "cvr_pct": 3, "ctr_pct": 1.5},
        "meta": {"roas": 0.8, "cps": 120, "l2s_pct": 7, "cvr_pct": 0.5, "ctr_pct": 0.7},
        "bing": {"roas": 1.7, "cps": 70, "l2s_pct": 19, "cvr_pct": 2.9, "ctr_pct": 1.4},
        "google_funnels": {},
        "meta_funnels": {},
        "bing_funnels": {},
        "totals": {
            "revenue": 2400,
            "cost": 1200,
            "sales": 24,
            "roas": 2,
            "cps": 50,
            "l2s_pct": 16,
            "cvr_pct": 3,
            "aov": 100,
        },
    }
    insights = {
        "slide3_general_insights": "",
        "slide3_budget_roas": "",
        "slide3_strategy": "",
        "performance_manager_narrative": "",
        "action_items": [],
    }

    replacements = build_slides_replacements(
        "One Funded",
        "March",
        2026,
        "February",
        "April",
        kpis,
        insights,
        {
            "company_revenue": 5000,
            "prev_company_revenue": 4000,
            "prev_ad_revenue": 2000,
            "prev_ad_cost": 1000,
        },
        prev_kpis=prev_kpis,
    )

    assert replacements["{{COMPANY_REVENUE_PREV}}"] == "$0.00"
    assert replacements["{{PCT_REV_FROM_ADS_PREV}}"] == "0%"
    assert replacements["{{SLIDE4_AD_REVENUE_PREV}}"] == "$2,000.00"
    assert replacements["{{SLIDE4_AD_COST_PREV}}"] == "$1,000.00"
    assert replacements["{{SLIDE4_ROAS_PREV}}"] == "2.00"
    assert replacements["{{SLIDE4_CPS_PREV}}"] == "$41.67"
    assert replacements["{{GOOGLE_CPS_PREV}}"] == "$40.00"
    assert replacements["{{META_L2S_PREV}}"] == "7.00%"
    assert replacements["{{BING_CVR_PREV}}"] == "2.90%"
