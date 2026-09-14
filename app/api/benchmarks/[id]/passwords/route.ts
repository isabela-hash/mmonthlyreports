import { NextRequest, NextResponse } from "next/server";
import { isAuthenticated } from "@/lib/auth";
import { REPORT_ID, sameOrigin } from "@/lib/benchmark-auth";
import { runReportOps } from "@/lib/python";
export const dynamic = "force-dynamic";
export const maxDuration = 60;
export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const headers = { "Cache-Control": "private, no-store" };
  if (!await isAuthenticated() || !sameOrigin(request.headers)) return NextResponse.json({ error: "Portal login required" }, { status: 401, headers });
  const { id } = await params;
  if (!REPORT_ID.test(id)) return NextResponse.json({ error: "Report not found" }, { status: 404, headers });
  try { return NextResponse.json(await runReportOps("benchmark-passwords", { id }), { headers }); }
  catch { return NextResponse.json({ error: "Report passwords unavailable; check seed configuration" }, { status: 503, headers }); }
}
