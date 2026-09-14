import { NextResponse } from "next/server";
import { assertAuthenticated } from "@/lib/auth";
import { runReportOps } from "@/lib/python";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function GET() {
  try {
    await assertAuthenticated();
    const result = await runReportOps("alpha-geo-performance");
    return NextResponse.json(result, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json(
      { status: "error", error: message },
      { status: message === "Unauthorized" ? 401 : 500 },
    );
  }
}
