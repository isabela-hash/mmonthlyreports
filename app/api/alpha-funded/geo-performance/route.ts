import { NextResponse } from "next/server";
export const dynamic = "force-dynamic";
export async function GET() {
  return NextResponse.json({ error: "Campaign-name geography has been retired. Use the country benchmark archive at /benchmarks." }, { status: 410, headers: { "Cache-Control": "no-store" } });
}
