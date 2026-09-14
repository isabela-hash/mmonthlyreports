export type Source = "hyros" | "meta" | "google";
export type Values = { spend: number | null; clicks: number | null; revenue: number | null; sales: number | null; leads: number | null };
export type Row = Values & { client: string; month: string; country: string; region: string; source: Source };
export type Client = { code: string; name?: string; prop_verified: boolean };
export type Report = { id: string; months: string[]; currency: string; created_at: string; rows: Row[]; clients: Client[]; refresh: string; failed_sources: number; provenance?: unknown[] };
export const metricNames = { cps: "CPS", cpc: "CPC", aov: "AOV", cpl: "CPL", roas: "ROAS" };
export type Metric = keyof typeof metricNames;
const ratios = { cps: ["spend", "sales"], cpc: ["spend", "clicks"], aov: ["revenue", "sales"], cpl: ["spend", "leads"], roas: ["revenue", "spend"] } as const;
export function totals(rows: Row[]): Values {
  return Object.fromEntries((["spend", "clicks", "revenue", "sales", "leads"] as const).map(key => [key, rows.length && rows.every(r => r[key] !== null) ? rows.reduce((sum, r) => sum + (r[key] ?? 0), 0) : null])) as Values;
}
export function metrics(rows: Row[]) {
  const values = totals(rows);
  return Object.fromEntries(Object.entries(ratios).map(([key, [a, b]]) => [key, values[a] !== null && values[b] !== null && values[b]! > 0 ? values[a]! / values[b]! : null])) as Record<Metric, number | null>;
}
function percentile(values: number[], p: number) {
  const sorted = [...values].sort((a, b) => a - b), i = (sorted.length - 1) * p;
  return sorted[Math.floor(i)] + (sorted[Math.ceil(i)] - sorted[Math.floor(i)]) * (i % 1);
}
export function benchmark(rows: Row[], clients: Client[], metric: Metric) {
  const values = clients.filter(c => c.prop_verified).map(c => metrics(rows.filter(r => r.client === c.code && r.country !== "ZZ"))[metric]).filter((v): v is number => v !== null);
  return { count: values.length, median: values.length >= 5 ? percentile(values, .5) : null, q1: values.length >= 5 ? percentile(values, .25) : null, q3: values.length >= 5 ? percentile(values, .75) : null };
}
