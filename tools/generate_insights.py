from __future__ import annotations

# tools/generate_insights.py
import json
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - exercised when dependency is not installed locally.
    OpenAI = None

ANTHROPIC_DEFAULT_MODEL = os.environ.get("ANTHROPIC_INSIGHTS_MODEL", "claude-sonnet-4-6")
ANTHROPIC_MAX_TOKENS = int(os.environ.get("ANTHROPIC_INSIGHTS_MAX_TOKENS", "8192"))
OPENAI_DEFAULT_MODEL = os.environ.get("OPENAI_INSIGHTS_MODEL", "gpt-5.4-mini")
INSIGHT_PROVIDER_TIMEOUT_SECONDS = float(os.environ.get("REPORT_INSIGHTS_TIMEOUT_SECONDS", "90"))
INSIGHT_PROVIDER_CHOICES = {"deterministic", "anthropic", "openai", "auto"}


class InsightProviderError(RuntimeError):
    """Raised when a requested insight provider cannot be used."""

class _NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        try:
            import numpy as np
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
        except ImportError:
            pass
        return super().default(obj)

def _dumps(obj, **kwargs):
    return json.dumps(obj, cls=_NumpyEncoder, **kwargs)


def _load_json_response(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())

def build_prompt(
    client: str,
    month: str,
    year: int,
    prev_month: str,
    prev_year: int | None,
    kpis: dict,
    user_overrides: dict,
    media_buyer_notes: str = "",
    special_requests: str = "",
    currency: str = "USD",
) -> str:
    currency = (currency or "USD").upper()
    bing = kpis.get("bing", {})
    bing_funnels = kpis.get("bing_funnels", {})
    return f"""You are a senior performance marketing analyst for prop firms.
Company: {client}
Report Month: {month} {year}
Previous Month: {prev_month} {prev_year or year}
Currency for all money values: {currency}

=== CURRENT MONTH KPIs ===
Google: Revenue ${kpis['google']['revenue']:,.2f} | Cost ${kpis['google']['cost']:,.2f} | ROAS {kpis['google']['roas']} | Sales {int(kpis['google']['sales'])} | CPS ${kpis['google']['cps']:,.2f} | L2S {kpis['google']['l2s_pct']}% | CVR {kpis['google']['cvr_pct']}% | CTR {kpis['google']['ctr_pct']}%
Meta:   Revenue ${kpis['meta']['revenue']:,.2f} | Cost ${kpis['meta']['cost']:,.2f} | ROAS {kpis['meta']['roas']} | Sales {int(kpis['meta']['sales'])} | CPS ${kpis['meta']['cps']:,.2f} | L2S {kpis['meta']['l2s_pct']}% | CVR {kpis['meta']['cvr_pct']}% | CTR {kpis['meta']['ctr_pct']}%
Bing:   Revenue ${bing.get('revenue', 0):,.2f} | Cost ${bing.get('cost', 0):,.2f} | ROAS {bing.get('roas', 0)} | Sales {int(bing.get('sales', 0))} | CPS ${bing.get('cps', 0):,.2f} | L2S {bing.get('l2s_pct', 0)}% | CVR {bing.get('cvr_pct', 0)}% | CTR {bing.get('ctr_pct', 0)}%
Total:  Revenue ${kpis['totals']['revenue']:,.2f} | Cost ${kpis['totals']['cost']:,.2f} | ROAS {kpis['totals']['roas']}

=== FUNNEL BREAKDOWN ===
Google TOF: {_dumps(kpis['google_funnels'].get('TOF', {}))}
Google MOF: {_dumps(kpis['google_funnels'].get('MOF', {}))}
Google BOF: {_dumps(kpis['google_funnels'].get('BOF', {}))}
Meta TOF: {_dumps(kpis['meta_funnels'].get('TOF', {}))}
Meta MOF: {_dumps(kpis['meta_funnels'].get('MOF', {}))}
Meta BOF: {_dumps(kpis['meta_funnels'].get('BOF', {}))}
Bing TOF: {_dumps(bing_funnels.get('TOF', {}))}
Bing MOF: {_dumps(bing_funnels.get('MOF', {}))}
Bing BOF: {_dumps(bing_funnels.get('BOF', {}))}

=== TOP FUNNEL ADS BY REVENUE ===
Google funnel ads: {_dumps(kpis.get('google_funnel_cards', {}), indent=2)}
Meta funnel ads: {_dumps(kpis.get('meta_funnel_cards', {}), indent=2)}
Bing funnel ads: {_dumps(kpis.get('bing_funnel_cards', {}), indent=2)}

=== TOTAL FUNNEL DISTRIBUTION ===
{_dumps(kpis.get('total_funnel_distribution', {}), indent=2)}

=== TOP ADS (Google) ===
{_dumps(kpis['google_top_ads'][:5], indent=2)}

=== TOP ADS (Meta) ===
{_dumps(kpis['meta_top_ads'][:5], indent=2)}

=== TOP ADS (Bing) ===
{_dumps(kpis.get('bing_top_ads', [])[:5], indent=2)}

=== USER OVERRIDES (Slide 4 only) ===
Company Revenue: ${user_overrides.get('company_revenue', 0):,.2f}
Ad Revenue: ${user_overrides.get('ad_revenue', 0):,.2f}
Ad Cost: ${user_overrides.get('ad_cost', 0):,.2f}

=== MEDIA BUYER NOTES ===
{media_buyer_notes or 'None provided.'}

=== SPECIAL REQUESTS ===
{special_requests or 'None.'}

Generate the following JSON. Every insight MUST follow DATA → INSIGHT → ACTION framework. Use exact numbers. Never be generic.
Return compact valid JSON only. Escape line breaks inside string values as \\n; do not put literal newlines inside JSON strings.
For every *_narrative field, write one complete slide-ready paragraph block with this structure:
line 1: "1.3M Impressions | 6.1K Clicks | 641.0 Leads | 119 Sales | $7.6K Ad Revenue | $10.9K Ad Spend | $91.7 CPS | 0.7 ROAS"
line 2: "Distribution: 65.6% ad spend, 22.2% ad revenue, and 27.8% of sales."
line 3: "Top Performer: [ad/campaign name] reached a [ROAS] ROAS, [sales] sales and [revenue] revenue, which is around [pct]% of funnel stage revenue."
line 4: "Next Steps: [specific optimization action]."
Use the requested currency symbol implied by Currency. If a funnel has no sales, write "No data CPS".

{{
  "slide3_general_insights": "...",
  "slide3_budget_roas": "...",
  "slide3_strategy": "...",
  "google_top_performer": "...",
  "google_main_drop": "...",
  "google_next_steps": "...",
  "meta_top_performer": "...",
  "meta_main_drop": "...",
  "meta_next_steps": "...",
  "google_tof_narrative": "...",
  "google_mof_narrative": "...",
  "google_bof_narrative": "...",
  "meta_tof_narrative": "...",
  "meta_mof_narrative": "...",
  "meta_bof_narrative": "...",
  "bing_tof_narrative": "...",
  "bing_mof_narrative": "...",
  "bing_bof_narrative": "...",
  "performance_manager_narrative": "...",
  "action_items": ["...", "...", "...", "...", "..."]
}}"""


def generate_insights(
    client: str,
    month: str,
    year: int,
    prev_month: str,
    prev_year: int | None,
    kpis: dict,
    user_overrides: dict,
    media_buyer_notes: str = "",
    special_requests: str = "",
    currency: str = "USD",
) -> dict:
    """Call Anthropic and return parsed JSON dict of slide narratives."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise InsightProviderError("ANTHROPIC_API_KEY is required to use the Anthropic insight provider.")
    client_sdk = anthropic.Anthropic(api_key=api_key, timeout=INSIGHT_PROVIDER_TIMEOUT_SECONDS)

    prompt = build_prompt(
        client, month, year, prev_month, prev_year,
        kpis, user_overrides, media_buyer_notes, special_requests, currency
    )

    response = client_sdk.messages.create(
        model=ANTHROPIC_DEFAULT_MODEL,
        max_tokens=ANTHROPIC_MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": "You are a senior performance marketing analyst specialized in paid media for prop firms. Always respond with valid JSON only. No markdown code blocks, no preamble.",
                "cache_control": {"type": "ephemeral"}
            }
        ],
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    return _load_json_response(raw)


def generate_openai_insights(
    client: str,
    month: str,
    year: int,
    prev_month: str,
    prev_year: int | None,
    kpis: dict,
    user_overrides: dict,
    media_buyer_notes: str = "",
    special_requests: str = "",
    currency: str = "USD",
) -> dict:
    """Call the OpenAI Responses API and return parsed JSON dict of slide narratives."""
    if OpenAI is None:
        raise InsightProviderError("The openai package is not installed. Add it to the runtime dependencies first.")

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise InsightProviderError("OPENAI_API_KEY is required to use the OpenAI insight provider.")

    prompt = build_prompt(
        client,
        month,
        year,
        prev_month,
        prev_year,
        kpis,
        user_overrides,
        media_buyer_notes,
        special_requests,
        currency,
    )
    instructions = (
        "You are a senior performance marketing analyst specialized in paid media for prop firms. "
        "Respond with valid JSON only. No markdown code blocks and no preamble."
    )
    client_sdk = OpenAI(api_key=api_key, timeout=INSIGHT_PROVIDER_TIMEOUT_SECONDS)
    response = client_sdk.responses.create(
        model=OPENAI_DEFAULT_MODEL,
        input=f"{instructions}\n\n{prompt}",
        reasoning={"effort": "none"},
        text={"verbosity": "low"},
        store=False,
    )
    return _load_json_response(response.output_text)


def generate_insights_with_provider(
    provider: str,
    *,
    client: str,
    month: str,
    year: int,
    prev_month: str,
    prev_year: int | None = None,
    kpis: dict,
    user_overrides: dict,
    media_buyer_notes: str = "",
    special_requests: str = "",
    currency: str = "USD",
    deterministic_factory=None,
) -> tuple[dict, str]:
    """Resolve a provider choice and return both insights and the provider actually used."""
    normalized_provider = (provider or "deterministic").strip().lower()
    if normalized_provider not in INSIGHT_PROVIDER_CHOICES:
        raise ValueError(
            f"Unsupported insights provider {provider!r}. Expected one of {sorted(INSIGHT_PROVIDER_CHOICES)}."
        )

    deterministic_factory = deterministic_factory or (lambda: None)

    payload = {
        "client": client,
        "month": month,
        "year": year,
        "prev_month": prev_month,
        "prev_year": prev_year,
        "kpis": kpis,
        "user_overrides": user_overrides,
        "media_buyer_notes": media_buyer_notes,
        "special_requests": special_requests,
        "currency": currency,
    }

    if normalized_provider == "deterministic":
        return deterministic_factory(), "deterministic"
    if normalized_provider == "anthropic":
        return generate_insights(**payload), "anthropic"
    if normalized_provider == "openai":
        return generate_openai_insights(**payload), "openai"

    errors = []
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        try:
            return generate_insights(**payload), "anthropic"
        except Exception as exc:
            errors.append(f"Anthropic failed: {exc}")

    if os.environ.get("OPENAI_API_KEY", "").strip():
        try:
            return generate_openai_insights(**payload), "openai"
        except Exception as exc:
            errors.append(f"OpenAI failed: {exc}")

    if errors:
        raise InsightProviderError("; ".join(errors))
    raise InsightProviderError("INSIGHTS_PROVIDER=auto requires ANTHROPIC_API_KEY or OPENAI_API_KEY.")
