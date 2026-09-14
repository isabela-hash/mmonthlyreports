import { NextRequest, NextResponse } from "next/server";
import { createReportToken, sameOrigin, reportCookie, validScope, verifyReportPassword } from "@/lib/benchmark-auth";
import { runReportOps } from "@/lib/python";
export const dynamic = "force-dynamic";
export const maxDuration = 60;
export async function POST(request: NextRequest, context: { params: Promise<{ id: string; view: string }> }) {
  const { id, view } = await context.params;
  const headers = { "Cache-Control": "private, no-store" };
  if (!validScope(id, view)) return NextResponse.json({ error: "Report not found" }, { status: 404, headers });
  if (!sameOrigin(request.headers)) return NextResponse.json({ error: "Invalid origin" }, { status: 403, headers });
  try {
    const text = await request.text();
    if (text.length > 1024) return NextResponse.json({ error: "Invalid request" }, { status: 400, headers });
    const { password } = JSON.parse(text);
    if (typeof password !== "string") return NextResponse.json({ error: "Password required" }, { status: 400, headers });
    const result = await runReportOps<{ hash: string }>("benchmark-access", { id, view });
    if (!await verifyReportPassword(password, result.hash)) return NextResponse.json({ error: "Incorrect password" }, { status: 401, headers });
    const response = NextResponse.json({ ok: true }, { headers });
    response.cookies.set(reportCookie(id, view), createReportToken(id, view), { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "strict", path: "/", maxAge: 36000 });
    return response;
  } catch { return NextResponse.json({ error: "Report access is not available yet" }, { status: 503, headers }); }
}
