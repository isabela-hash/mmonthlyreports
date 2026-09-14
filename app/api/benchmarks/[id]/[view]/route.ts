import { NextRequest, NextResponse } from "next/server";
import { reportCookie, validScope, verifyReportToken } from "@/lib/benchmark-auth";
import { isAuthenticated } from "@/lib/auth";
import { runReportOps } from "@/lib/python";
export const dynamic = "force-dynamic";
export const maxDuration = 60;
export async function GET(request: NextRequest, context: { params: Promise<{ id: string; view: string }> }) {
  const { id, view } = await context.params;
  const headers = { "Cache-Control": "private, no-store", "X-Robots-Tag": "noindex, nofollow", "Vary": "Cookie" };
  if (!validScope(id, view)) return NextResponse.json({ error: "Report not found" }, { status: 404, headers });
  const authorized = verifyReportToken(request.cookies.get(reportCookie(id, view))?.value, id, view) || (view === "private" && await isAuthenticated());
  if (!authorized) return NextResponse.json({ error: "Password required" }, { status: 401, headers });
  try {
    const result = await runReportOps("benchmark-read", { id, view });
    return NextResponse.json(result, { headers });
  } catch { return NextResponse.json({ error: "Snapshot unavailable. No report data has been substituted." }, { status: 503, headers }); }
}
