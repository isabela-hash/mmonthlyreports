import { NextResponse } from "next/server";
import { assertAuthenticated } from "@/lib/auth";
import { runReportOps } from "@/lib/python";
import type { CommandAction } from "@/lib/commands";

export const maxDuration = 300;

const actionToCommand: Partial<Record<CommandAction, string>> = {
  "create-client": "create-client",
  preflight: "preflight",
  dashboard: "dashboard",
  "set-active": "set-active",
};

export async function POST(request: Request) {
  try {
    await assertAuthenticated();
    const body = await request.json().catch(() => ({}));
    const action = String(body.action || "") as CommandAction;
    const payload = (body.payload || {}) as Record<string, unknown>;
    if (payload.allow_first_month_baseline && !payload.confirm_first_month_baseline) {
      return NextResponse.json(
        { status: "error", error: "First-month baseline requires explicit confirmation." },
        { status: 400 },
      );
    }
    if (action === "run-one" || action === "run-missing" || action === "run-all") {
      const runMode = action === "run-one" ? "one" : action === "run-all" ? "all" : "missing";
      const result = await runReportOps("run-report", { ...payload, run_mode: runMode });
      return NextResponse.json(result);
    }
    const command = actionToCommand[action];
    if (!command) {
      return NextResponse.json({ status: "error", error: "Unsupported action." }, { status: 400 });
    }
    const result = await runReportOps(command, payload);
    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ status: "error", error: message }, { status: message === "Unauthorized" ? 401 : 400 });
  }
}
