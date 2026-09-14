import { NextResponse } from "next/server";
import { assertAuthenticated } from "@/lib/auth";
import { runReportOps } from "@/lib/python";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function GET(request: Request) {
  try {
    await assertAuthenticated();
    const url = new URL(request.url);
    const payload = {
      month: url.searchParams.get("month") || undefined,
      year: url.searchParams.get("year") || undefined,
    };
    const result = await runReportOps("dashboard", payload);
    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ status: "error", error: message }, { status: message === "Unauthorized" ? 401 : 500 });
  }
}
