import { NextResponse } from "next/server";
import { assertAuthenticated } from "@/lib/auth";
import { runReportOps } from "@/lib/python";

export const maxDuration = 300;

export async function POST(request: Request) {
  try {
    await assertAuthenticated();
    const body = await request.json().catch(() => ({}));
    if (body.allow_first_month_baseline && !body.confirm_first_month_baseline) {
      return NextResponse.json(
        { status: "error", error: "First-month baseline requires explicit confirmation." },
        { status: 400 },
      );
    }
    const result = await runReportOps("run-report", body);
    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ status: "error", error: message }, { status: message === "Unauthorized" ? 401 : 400 });
  }
}
