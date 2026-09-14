import crypto from "node:crypto";
export type ReportView = "private" | "share";
export const REPORT_ID = /^\d{4}-(0[1-9]|1[0-2])-r[1-9]\d{0,3}$/;
export function validScope(id: string, view: string): view is ReportView {
  return REPORT_ID.test(id) && (view === "private" || view === "share");
}
function secret() {
  const value = process.env.BENCHMARK_SESSION_SECRET;
  if (!value || value.length < 32) throw new Error("Report access is not configured");
  return value;
}
function signature(value: string) { return crypto.createHmac("sha256", secret()).update(value).digest("base64url"); }
function equal(a: string, b: string) {
  const x = Buffer.from(a), y = Buffer.from(b);
  return x.length === y.length && crypto.timingSafeEqual(x, y);
}
export function createReportToken(id: string, view: ReportView, now = Date.now()) {
  if (!validScope(id, view)) throw new Error("Invalid scope");
  const payload = Buffer.from(JSON.stringify({ id, view, exp: Math.floor(now / 1000) + 36000 })).toString("base64url");
  return `${payload}.${signature(payload)}`;
}
export function verifyReportToken(token: string | undefined, id: string, view: ReportView, now = Date.now()) {
  try {
    if (!token || !validScope(id, view)) return false;
    const parts = token.split(".");
    if (parts.length !== 2 || !equal(signature(parts[0]), parts[1])) return false;
    const value = JSON.parse(Buffer.from(parts[0], "base64url").toString());
    return value.id === id && value.view === view && typeof value.exp === "number" && value.exp > now / 1000;
  } catch { return false; }
}
export function reportCookie(id: string, view: ReportView) { return `mm_report_${id}_${view}`; }
export async function verifyReportPassword(password: string, stored: string) {
  if (password.length > 256 || !/^[a-f0-9]{32}:[a-f0-9]{128}$/.test(stored)) return false;
  const [salt, digest] = stored.split(":");
  const derived = await new Promise<Buffer>((resolve, reject) => {
    crypto.scrypt(password, Buffer.from(salt, "hex"), 64, { N: 16384, r: 8, p: 1 }, (error, key) => error ? reject(error) : resolve(key));
  });
  return equal(derived.toString("hex"), digest);
}

export function sameOrigin(headers: Headers) {
  try {
    const origin = new URL(headers.get("origin") || "");
    return origin.host === headers.get("host") && (origin.protocol === "https:" || (process.env.NODE_ENV !== "production" && origin.protocol === "http:"));
  } catch { return false; }
}
