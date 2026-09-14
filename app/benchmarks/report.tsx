"use client";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { benchmark, Client, Metric, metricNames, metrics, Report, Row, Source, totals } from "@/lib/benchmark-data";
import styles from "./report.module.css";
const metricKeys = Object.keys(metricNames) as Metric[];
const definitions = { cps: "Spend ÷ sales", cpc: "Spend ÷ clicks", aov: "Revenue ÷ sales", cpl: "Spend ÷ leads", roas: "Revenue ÷ spend" };
const countryNames = new Intl.DisplayNames(["en"], { type: "region" });
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
function display(value: number | null, key: Metric = "cps") { return value === null ? "Unavailable" : key === "roas" ? `${value.toFixed(2)}×` : money.format(value); }
function countryName(code: string) { return code === "ZZ" ? "Unknown country" : countryNames.of(code) || code; }
function monthName(month: string) { return new Date(`${month}-01T12:00:00Z`).toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" }); }
function clientName(client: Client) { return client.name ? `${client.name} · ${client.code}` : client.code; }
function download(rows: Row[], clients: Client[], id: string) {
  const heading = ["Client", "Source", "Month", "Country", "Region", "Currency", "Spend", "Clicks", "Revenue", "Sales", "Leads", ...Object.values(metricNames)];
  const escape = (value: unknown) => { let text = value == null ? "Unavailable" : String(value); if (/^[=+@\-]/.test(text)) text = "'" + text; return '"' + text.replaceAll('"', '""') + '"'; };
  const lines = rows.map(row => [clientName(clients.find(c => c.code === row.client)!), row.source, row.month, countryName(row.country), row.region, "USD", row.spend, row.clicks, row.revenue, row.sales, row.leads, ...metricKeys.map(k => metrics([row])[k])]);
  const blob = new Blob([[heading, ...lines].map(row => row.map(escape).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob), a = document.createElement("a"); a.href = url; a.download = `country-benchmarks-${id}.csv`; a.click(); URL.revokeObjectURL(url);
}
export default function BenchmarkReport({ id, view }: { id: string; view: "private" | "share" }) {
  const [report, setReport] = useState<Report | null>(null), [locked, setLocked] = useState(false), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const [password, setPassword] = useState(""), [source, setSource] = useState<Source>("hyros"), [region, setRegion] = useState(""), [client, setClient] = useState(""), [month, setMonth] = useState(""), [search, setSearch] = useState(""), [cohort, setCohort] = useState("all");
  const [sort, setSort] = useState<Metric>("roas");
  const endpoint = `/api/benchmarks/${id}/${view}`;
  const load = useCallback(async () => {
    setError("");
    try { const response = await fetch(endpoint, { cache: "no-store" }); const data = await response.json();
      if (response.status === 401) { setLocked(true); return; }
      if (!response.ok) throw new Error(data.error || "Unable to load snapshot");
      setReport(data); setLocked(false);
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to load snapshot"); }
  }, [endpoint]);
  useEffect(() => { void load(); }, [load]);
  const filtered = useMemo(() => report?.rows.filter(row => row.source === source && (!month || row.month === month) && (!client || row.client === client) && (!region || row.region === region) && (cohort === "all" || report.clients.find(c => c.code === row.client)?.prop_verified) && countryName(row.country).toLowerCase().includes(search.toLowerCase().trim())) || [], [report, source, month, client, region, cohort, search]);
  const known = filtered.filter(r => r.country !== "ZZ"), values = metrics(known), volume = totals(known);
  if (!report) return <main className={styles.gate}><div><span className={styles.brand}>MODERNIZED</span><h1>Country benchmarks</h1><p>{id} · {view === "private" ? "Private client view" : "Shareable data view"}</p>
    {locked && <form onSubmit={async event => { event.preventDefault(); setBusy(true); setError(""); try { const response = await fetch(`${endpoint}/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }) }); const data = await response.json(); if (!response.ok) throw new Error(data.error); setPassword(""); await load(); } catch (e) { setError(e instanceof Error ? e.message : "Unable to sign in"); } finally { setBusy(false); } }}>
      <label htmlFor="report-password">Report password</label><input id="report-password" type="password" autoComplete="current-password" required maxLength={256} value={password} onChange={e => setPassword(e.target.value)} /><button disabled={busy}>{busy ? "Opening…" : "Open report →"}</button></form>}
    {!locked && !error && <p role="status">Loading verified snapshot…</p>}{error && <p role="alert">{error}</p>}{!locked && error && <button onClick={load}>Try again</button>}
  </div></main>;
  const regions = [...new Set(report.rows.filter(r => r.source === source).map(r => r.region))].sort();
  const countries = [...new Set(filtered.map(r => r.country))].map(code => ({ code, rows: filtered.filter(r => r.country === code) })).sort((a, b) => (metrics(b.rows)[sort] ?? -Infinity) - (metrics(a.rows)[sort] ?? -Infinity));
  const period = month ? monthName(month) : `${monthName(report.months[0])} – ${monthName(report.months.at(-1)!)}`;
  return <main className={styles.page}>
    <header className={styles.header}><div><span className={styles.brand}>MODERNIZED</span><h1>Country benchmarks</h1><p>{period} <span> / </span> USD <span> / </span> {view === "private" ? "Private client view" : "Shareable data view"}</p></div><div className={styles.actions}>{view === "private" && <Link href="/benchmarks">Monthly archive</Link>}<button onClick={() => download(filtered, report.clients, id)}>Export this view ↓</button></div></header>
    <div className={styles.sources} aria-label="Attribution source">{(["hyros", "meta", "google"] as Source[]).map(s => <button key={s} aria-pressed={source === s} onClick={() => { setSource(s); setRegion(""); }}>{s === "hyros" ? "Hyros attribution" : s === "meta" ? "Meta only" : "Google Ads only"}</button>)}</div>
    <div className={styles.filters}>
      <label>Region<select value={region} onChange={e => setRegion(e.target.value)}><option value="">All regions</option>{regions.map(r => <option key={r}>{r}</option>)}</select></label>
      <label>Client<select value={client} onChange={e => setClient(e.target.value)}><option value="">All clients</option>{report.clients.map(c => <option key={c.code} value={c.code}>{clientName(c)}</option>)}</select></label>
      <label>Period<select value={month} onChange={e => setMonth(e.target.value)}><option value="">Six months</option>{report.months.map(m => <option key={m} value={m}>{monthName(m)}</option>)}</select></label>
      <label>Business group<select value={cohort} onChange={e => setCohort(e.target.value)}><option value="all">All clients</option><option value="prop">Verified prop firms</option></select></label>
      <label>Find a country<input placeholder="e.g. United States" value={search} onChange={e => setSearch(e.target.value)} type="search" /></label>
      <button className={styles.reset} onClick={() => { setRegion(""); setClient(""); setMonth(""); setSearch(""); setCohort("all"); }}>Reset</button>
    </div>
    <p className={styles.status}>{new Set(known.map(r => r.client)).size} of {report.clients.length} clients with known-country data · {new Set(known.map(r => r.month)).size} months available · {report.refresh === "api" ? "API snapshot" : "Dated source exports"} · Captured {new Date(report.created_at).toLocaleDateString("en-GB")}</p>
    {!!report.failed_sources && <p className={styles.notice}>Partial refresh: {report.failed_sources} source connections failed. Totals cover available records only.</p>}
    <div className={styles.cards}>{metricKeys.map(key => { const band = benchmark(known, report.clients, key); return <section key={key} className={styles.card}><div>{metricNames[key]} <small title={definitions[key]} aria-label={definitions[key]}>ⓘ</small></div><strong>{display(values[key], key)}</strong><p>{definitions[key]}</p><footer>{band.count >= 5 ? <>Prop median {display(band.median, key)}<br />Middle 50% {display(band.q1, key)}–{display(band.q3, key)}</> : <>Limited sample<br />{band.count}/5 prop clients for a range</>}</footer></section>; })}</div>
    <p className={styles.status}>Known-country totals: {volume.spend === null ? "spend unavailable" : `${money.format(volume.spend)} spend`} · {volume.sales === null ? "sales unavailable" : `${volume.sales.toLocaleString("en-US", { maximumFractionDigits: 2 })} sales`} · {filtered.filter(r => r.country === "ZZ").length} unknown-country records excluded from KPI cards and benchmarks.</p>
    {!filtered.length ? <section className={styles.panel}><h2>No verified data for this selection</h2><p>Try another source or clear the filters. Missing history is not counted as zero.</p></section> : <>
      <section className={styles.panel}><div className={styles.sectionHead}><h2>Countries</h2><label>Order by<select value={sort} onChange={e => setSort(e.target.value as Metric)}>{metricKeys.map(k => <option key={k} value={k}>{metricNames[k]}</option>)}</select></label></div><div className={styles.tableScroll}><table><thead><tr><th>Country</th><th>Region</th><th>Clients</th><th>Spend</th>{metricKeys.map(k => <th key={k}>{metricNames[k]}</th>)}</tr></thead><tbody>{countries.map(({ code, rows }) => { const m = metrics(rows); return <tr key={code}><th>{countryName(code)}</th><td>{rows[0].region}</td><td>{new Set(rows.map(r => r.client)).size}</td><td>{display(totals(rows).spend)}</td>{metricKeys.map(k => <td key={k}>{display(m[k], k)}</td>)}</tr>; })}</tbody></table></div></section>
      <section className={styles.panel}><h2>Regional comparison</h2><div className={styles.tableScroll}><table><thead><tr><th>Region / contributing countries</th>{metricKeys.map(k => <th key={k}>{metricNames[k]}</th>)}</tr></thead><tbody>{[...new Set(known.map(r => r.region))].sort().map(r => { const rows = known.filter(row => row.region === r), m = metrics(rows); return <tr key={r}><th><button className={styles.textButton} onClick={() => setRegion(r)}>{r} →</button><small>{[...new Set(rows.map(row => countryName(row.country)))].sort().join(", ")}</small></th>{metricKeys.map(k => <td key={k}>{display(m[k], k)}</td>)}</tr>; })}</tbody></table></div></section>
    </>}
    <section className={styles.panel}><h2>Client comparison & coverage</h2><div className={styles.tableScroll}><table><thead><tr><th>Client</th><th>Benchmark group</th><th>Available months</th>{metricKeys.map(k => <th key={k}>{metricNames[k]}</th>)}</tr></thead><tbody>{report.clients.filter(c => (!client || c.code === client) && (cohort === "all" || c.prop_verified)).map(c => { const rows = known.filter(r => r.client === c.code), m = metrics(rows); return <tr key={c.code}><th>{clientName(c)}</th><td>{c.prop_verified ? "Verified prop firm" : "Other / unverified"}</td><td>{[...new Set(rows.map(r => r.month))].sort().map(monthName).join(", ") || "No verified data"}</td>{metricKeys.map(k => <td key={k}>{display(m[k], k)}</td>)}</tr>; })}</tbody></table></div></section>
    <details className={styles.panel}><summary>Monthly metrics</summary><div className={styles.tableScroll}><table><thead><tr><th>Month</th>{metricKeys.map(k => <th key={k}>{metricNames[k]}</th>)}</tr></thead><tbody>{report.months.filter(m => !month || month === m).map(m => { const result = metrics(known.filter(r => r.month === m)); return <tr key={m}><th>{monthName(m)}</th>{metricKeys.map(k => <td key={k}>{display(result[k], k)}</td>)}</tr>; })}</tbody></table></div></details>
    <details className={styles.panel}><summary>Definitions, source coverage & methodology</summary><p>Metrics use ratios of summed values, in USD. A missing numerator or denominator makes the metric unavailable. Unknown geography remains in exports and the country table but is excluded from benchmark calculations. Platform country reflects the platform’s reported location, not independently verified billing residence.</p><p>Hyros, Meta and Google use separate attribution views. Their sales and revenue are never added together. Hyros spend-based metrics require explicitly compatible country-level spend. Meta CPC uses link clicks; Google CPC uses reported ad clicks.</p><p>Prop benchmarks use the unweighted distribution of verified client-level metrics. At least five contributing clients are required for a median and middle-50% range. Portfolio cards use pooled totals and may be dominated by larger clients. Every filter also applies to the benchmarks and export.</p><p>Regions follow UN M49 with USA, UK + Canada, India and UAE split out. Europe excludes the UK; Asia excludes India and UAE. Other and unknown countries remain visible.</p><p>External industry references: unavailable. No unverified industry advertising ranges have been substituted for client results.</p>{view === "private" && report.provenance && <details><summary>Private source records & currency conversion</summary><pre className={styles.provenance}>{JSON.stringify(report.provenance, null, 2)}</pre></details>}</details>
    <footer className={styles.footer}>Snapshot {id} · Previous monthly copies remain unchanged</footer>
  </main>;
}
