import { NextResponse } from "next/server";
import { assertAuthenticated } from "@/lib/auth";
import { buildConfirmationPlan } from "@/lib/commands";

export async function POST(request: Request) {
  try {
    await assertAuthenticated();
    const body = await request.json().catch(() => ({}));
    const prompt = String(body.prompt || body.preset || "");
    if (!prompt.trim()) {
      return NextResponse.json({ status: "error", error: "Prompt is required." }, { status: 400 });
    }
    return NextResponse.json({ status: "ok", plan: buildConfirmationPlan(prompt) });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ status: "error", error: message }, { status: message === "Unauthorized" ? 401 : 500 });
  }
}
