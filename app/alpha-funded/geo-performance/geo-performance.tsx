"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import styles from "./geo-performance.module.css";

type Measure = "Cost" | "Total Revenue" | "Click" | "Leads" | "Sales";
type Totals = Record<Measure, number>;
type Row = Totals & { month: string; region: string; campaign_rows: number };
type Snapshot = {
  status: string;
  period: string;
  months: string[];
  regions: string[];
  rows: Row[];
  source_url: string;
  read_at_utc: string;
  campaign_rows: number;
};

const MEASURES: Measure[] = ["Cost", "Total Revenue", "Click", "Leads", "Sales"];
const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
const integer = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const percent = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 1 });

function sumRows(rows: Row[]): Totals & { campaign_rows: number } {
  const totals = { Cost: 0, "Total Revenue": 0, Click: 0, Leads: 0, Sales: 0, campaign_rows: 0 };
  for (const row of rows) {
    for (const measure of MEASURES) totals[measure] += row[measure];
    totals.campaign_rows += row.campaign_rows;
  }
  return totals;
}

function moneyRatio(numerator: number, denominator: number) {
  return denominator > 0 ? usd.format(numerator / denominator) : "—";
}

function roas(revenue: number, cost: number) {
  return cost > 0 ? `${(revenue / cost).toFixed(2)}×` : "—";
}

export default function GeoPerformance() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [selectedMonth, setSelectedMonth] = useState("All 6 months");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/alpha-funded/geo-performance", { cache: "no-store" });
      if (response.status === 401) {
        window.location.href = "/login";
        return;
      }
      const result = (await response.json()) as Snapshot & { error?: string };
      if (!response.ok || result.status !== "ok") throw new Error(result.error || "Could not read the source sheet.");
      setSnapshot(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load the data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const filteredRows = useMemo(
    () => snapshot?.rows.filter((row) => selectedMonth === "All 6 months" || row.month === selectedMonth) || [],
    [snapshot, selectedMonth],
  );
  const total = useMemo(() => sumRows(filteredRows), [filteredRows]);
  const named = useMemo(
    () => sumRows(filteredRows.filter((row) => row.region !== "Mixed / unassigned")),
    [filteredRows],
  );
  const coverage = total.Cost > 0 ? named.Cost / total.Cost : null;
  const refreshed = snapshot ? new Date(snapshot.read_at_utc).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) : "";

  return (
    <main className={styles.page}>
      <div className={styles.frame}>
        <nav className={styles.nav} aria-label="Page navigation">
          <Link className={styles.back} href="/">← Report Ops</Link>
          <span className={styles.navLabel}>ALPHA FUNDED / GEO PERFORMANCE</span>
          <button className={styles.refresh} type="button" onClick={() => void refresh()} disabled={loading}>
            {loading ? "Reading sheet…" : "↻ Refresh data"}
          </button>
        </nav>

        <header className={styles.hero}>
          <div>
            <div className={styles.eyebrow}>CAMPAIGN GEOGRAPHY CHECK · {snapshot?.period.toUpperCase() || "MARCH–AUGUST 2026"}</div>
            <h1>Where is the ad spend <em>working?</em></h1>
            <p>Six complete months of Alpha Funded campaign data. These are campaign-name targeting labels, not verified customer locations.</p>
          </div>
          <div className={styles.heroStat}>
            <span>GEO-ATTRIBUTABLE SPEND</span>
            <strong>{coverage === null ? "—" : percent.format(coverage)}</strong>
            <small>{coverage === null ? "Waiting for data" : `${usd.format(total.Cost - named.Cost)} is mixed or unlabeled`}</small>
          </div>
        </header>

        {error && <div className={styles.error} role="alert">Source check failed: {error}. No numbers are being shown.</div>}

        <section className={styles.toolbar} aria-label="Period and source">
          <div>
            <label htmlFor="geo-month">VIEW PERIOD</label>
            <select id="geo-month" value={selectedMonth} onChange={(event) => setSelectedMonth(event.target.value)} disabled={!snapshot}>
              <option>All 6 months</option>
              {snapshot?.months.map((month) => <option key={month}>{month}</option>)}
            </select>
          </div>
          <div className={styles.sourceMeta}>
            <span>{loading ? "Checking the live source…" : snapshot ? `${integer.format(total.campaign_rows)} campaign rows · updated ${refreshed}` : "No source data loaded"}</span>
            {snapshot && <a href={snapshot.source_url} target="_blank" rel="noopener noreferrer">Open source Sheet ↗</a>}
          </div>
        </section>

        <section className={styles.tableCard} aria-label="Geographic performance metrics">
          <div className={styles.tableIntro}>
            <div>
              <span className={styles.sectionNo}>01 / REGIONAL ECONOMICS</span>
              <h2>Performance by explicit geo label</h2>
            </div>
            <span className={styles.currency}>ALL MONEY IN USD</span>
          </div>
          <div className={styles.tableScroll}>
            <table>
              <thead><tr>
                <th scope="col">Region</th>
                <th scope="col">Ad spend</th>
                <th scope="col">CPS <small>cost / sale</small></th>
                <th scope="col">CPC <small>cost / click</small></th>
                <th scope="col">AOV <small>revenue / sale</small></th>
                <th scope="col">CPL <small>cost / lead</small></th>
                <th scope="col">ROAS <small>revenue / spend</small></th>
              </tr></thead>
              <tbody>
                {snapshot?.regions.map((region, index) => {
                  const values = sumRows(filteredRows.filter((row) => row.region === region));
                  const hasSpend = values.Cost > 0;
                  return <tr key={region} className={region === "Mixed / unassigned" ? styles.unassigned : ""}>
                    <th scope="row"><span className={styles.regionIndex}>{String(index + 1).padStart(2, "0")}</span>{region}<small>{hasSpend ? `${integer.format(values.Sales)} sales · ${integer.format(values.Leads)} leads` : values["Total Revenue"] > 0 ? `No spend · ${usd.format(values["Total Revenue"])} attributed revenue` : "No attributable spend"}</small></th>
                    <td>{hasSpend ? usd.format(values.Cost) : "—"}</td>
                    <td>{hasSpend ? moneyRatio(values.Cost, values.Sales) : "—"}</td>
                    <td>{hasSpend ? moneyRatio(values.Cost, values.Click) : "—"}</td>
                    <td>{hasSpend ? moneyRatio(values["Total Revenue"], values.Sales) : "—"}</td>
                    <td>{hasSpend ? moneyRatio(values.Cost, values.Leads) : "—"}</td>
                    <td className={styles.roas}>{hasSpend ? roas(values["Total Revenue"], values.Cost) : "—"}</td>
                  </tr>;
                })}
                {snapshot && <tr className={styles.total}>
                  <th scope="row">All campaigns</th>
                  <td>{usd.format(total.Cost)}</td>
                  <td>{moneyRatio(total.Cost, total.Sales)}</td>
                  <td>{moneyRatio(total.Cost, total.Click)}</td>
                  <td>{moneyRatio(total["Total Revenue"], total.Sales)}</td>
                  <td>{moneyRatio(total.Cost, total.Leads)}</td>
                  <td>{roas(total["Total Revenue"], total.Cost)}</td>
                </tr>}
              </tbody>
            </table>
          </div>
          {!snapshot && !error && <p className={styles.empty}>Reading March–August campaigns from the Alpha Funded Sheet…</p>}
        </section>

        <aside className={styles.notes}>
          <div><span className={styles.sectionNo}>02 / HOW TO READ THIS</span><h2>Useful, with one important limit.</h2></div>
          <div className={styles.noteGrid}>
            <p><strong>Geography is inferred from campaign names.</strong> The uploaded Sheet has no country field. “All Countries,” “World,” “Abroad,” unlabeled, and multi-region campaigns stay mixed / unassigned. These cannot prove where buyers live.</p>
            <p><strong>Ratios are calculated from totals.</strong> Cost per sale (CPS), click (CPC), and lead (CPL) use total spend divided by the matching count. Average order value (AOV) is total revenue per sale. Return on ad spend (ROAS) is total revenue divided by total spend—not the simple average of monthly ROAS.</p>
            <p><strong>Buckets are mutually exclusive.</strong> UK and Canada share a bucket; India and UAE have their own. Europe excludes the UK. Asia excludes India and UAE. A dash means no usable spend or denominator, not a zero result. Some zero-spend campaigns still have attributed revenue, so their ratios are withheld.</p>
          </div>
        </aside>
      </div>
    </main>
  );
}
