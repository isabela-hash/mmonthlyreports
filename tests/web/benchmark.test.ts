import test from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import { createReportToken, verifyReportToken, verifyReportPassword, validScope } from "../../lib/benchmark-auth";
import { benchmark, metrics, Row } from "../../lib/benchmark-data";
process.env.BENCHMARK_SESSION_SECRET = "a".repeat(32);
test("report tokens cannot cross report, revision or audience boundaries", () => {
  const now = 1_000_000, token = createReportToken("2026-09-r1", "share", now);
  assert.equal(verifyReportToken(token, "2026-09-r1", "share", now), true);
  assert.equal(verifyReportToken(token, "2026-09-r1", "private", now), false);
  assert.equal(verifyReportToken(token, "2026-10-r1", "share", now), false);
  assert.equal(verifyReportToken(token, "2026-09-r2", "share", now), false);
  assert.equal(verifyReportToken(token + "x", "2026-09-r1", "share", now), false);
  assert.equal(verifyReportToken(token, "2026-09-r1", "share", now + 36_000_001), false);
  assert.equal(validScope("../../secrets", "share"), false);
});
test("Python-compatible scrypt hashes verify, invalid passwords fail", async () => {
  const salt = "ab".repeat(16), digest = crypto.scryptSync("example-pass", Buffer.from(salt, "hex"), 64).toString("hex");
  assert.equal(await verifyReportPassword("example-pass", `${salt}:${digest}`), true);
  assert.equal(await verifyReportPassword("wrong", `${salt}:${digest}`), false);
});
const row: Row = { client: "Client A", source: "hyros", month: "2026-08", country: "US", region: "USA", spend: 100, revenue: 300, sales: 4, clicks: 20, leads: 10 };
test("UI recomputes weighted metrics with strict missing coverage", () => {
  assert.deepEqual(metrics([row]), { cps: 25, cpc: 5, aov: 75, cpl: 10, roas: 3 });
  assert.equal(metrics([row, { ...row, spend: 900, sales: 6 }]).cps, 100);
  assert.equal(metrics([row, { ...row, spend: null }]).roas, null);
  assert.equal(metrics([{ ...row, sales: 0 }]).cps, null);
});
test("benchmark requires five independent verified clients", () => {
  const clients = "ABCDE".split("").map(c => ({ code: `Client ${c}`, prop_verified: true }));
  const rows = clients.map((c, i) => ({ ...row, client: c.code, spend: (i + 1) * 100 }));
  assert.deepEqual(benchmark(rows, clients, "cps"), { count: 5, median: 75, q1: 50, q3: 100 });
  assert.equal(benchmark(rows.slice(1), clients, "cps").median, null);
});
test("passwords fail closed without production report secret", () => {
  const previous = process.env.BENCHMARK_SESSION_SECRET;
  delete process.env.BENCHMARK_SESSION_SECRET;
  assert.throws(() => createReportToken("2026-09-r1", "share"));
  process.env.BENCHMARK_SESSION_SECRET = previous;
});
