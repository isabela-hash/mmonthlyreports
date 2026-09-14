import { NextResponse } from "next/server";
import { assertAuthenticated } from "@/lib/auth";
import { runReportOps } from "@/lib/python";

export const maxDuration = 120;

export async function POST(request: Request) {
  try {
    await assertAuthenticated();
    const body = await request.json().catch(() => ({}));
    const result = await runReportOps("create-client", body);
    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ status: "error", error: message }, { status: message === "Unauthorized" ? 401 : 400 });
  }
}
