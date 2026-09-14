import { NextResponse } from "next/server";
import { createSessionToken, setSessionCookie, validatePassword } from "@/lib/auth";

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const password = String(body.password || "");
  if (!validatePassword(password)) {
    return NextResponse.json({ status: "error", error: "Invalid password" }, { status: 401 });
  }
  await setSessionCookie(createSessionToken());
  return NextResponse.json({ status: "ok" });
}
