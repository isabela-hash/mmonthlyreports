import crypto from "node:crypto";
import { cookies } from "next/headers";

const COOKIE_NAME = "mt_portal_session";
const SESSION_TTL_SECONDS = 60 * 60 * 10;

function getSecret() {
  return process.env.PORTAL_SESSION_SECRET || (process.env.NODE_ENV === "production" ? null : process.env.PORTAL_PASSWORD || "dev-portal-secret");
}

function sign(value: string) {
  const secret = getSecret();
  return secret ? crypto.createHmac("sha256", secret).update(value).digest("base64url") : null;
}

export function createSessionToken() {
  const payload = Buffer.from(
    JSON.stringify({ exp: Math.floor(Date.now() / 1000) + SESSION_TTL_SECONDS }),
  ).toString("base64url");
  const signature = sign(payload);
  if (!signature) {
    throw new Error("PORTAL_SESSION_SECRET must be configured in production.");
  }
  return `${payload}.${signature}`;
}

export function verifySessionToken(token?: string) {
  if (!token || !token.includes(".")) {
    return false;
  }
  const [payload, signature] = token.split(".");
  if (!payload || !signature || sign(payload) !== signature) {
    return false;
  }
  try {
    const decoded = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as { exp?: number };
    return typeof decoded.exp === "number" && decoded.exp > Math.floor(Date.now() / 1000);
  } catch {
    return false;
  }
}

export async function isAuthenticated() {
  const cookieStore = await cookies();
  return verifySessionToken(cookieStore.get(COOKIE_NAME)?.value);
}

export async function assertAuthenticated() {
  if (!(await isAuthenticated())) {
    throw new Error("Unauthorized");
  }
}

export async function setSessionCookie(token: string) {
  const cookieStore = await cookies();
  cookieStore.set(COOKIE_NAME, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_TTL_SECONDS,
  });
}

export async function clearSessionCookie() {
  const cookieStore = await cookies();
  cookieStore.set(COOKIE_NAME, "", {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
}

export function validatePassword(password: string) {
  const expected = process.env.PORTAL_PASSWORD || (process.env.NODE_ENV === "production" ? "" : "changeme");
  const input = Buffer.from(password);
  const target = Buffer.from(expected);
  return expected.length > 0 && input.length === target.length && crypto.timingSafeEqual(input, target);
}
