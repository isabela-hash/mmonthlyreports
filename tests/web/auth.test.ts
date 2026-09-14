import assert from "node:assert/strict";
import { test } from "node:test";
import { createSessionToken, validatePassword, verifySessionToken } from "../../lib/auth";

test("development fallback works locally, production requires configured credentials", () => {
  const before = {
    nodeEnv: process.env.NODE_ENV,
    password: process.env.PORTAL_PASSWORD,
    secret: process.env.PORTAL_SESSION_SECRET,
  };
  try {
    delete process.env.PORTAL_PASSWORD;
    delete process.env.PORTAL_SESSION_SECRET;
    Object.assign(process.env, { NODE_ENV: "development" });
    assert.equal(validatePassword("changeme"), true);
    assert.equal(verifySessionToken(createSessionToken()), true);

    Object.assign(process.env, { NODE_ENV: "production" });
    assert.equal(validatePassword("changeme"), false);
    assert.equal(verifySessionToken("invalid.token"), false);
    assert.throws(createSessionToken, /PORTAL_SESSION_SECRET/);

    process.env.PORTAL_PASSWORD = "configured-password";
    process.env.PORTAL_SESSION_SECRET = "configured-session-secret";
    assert.equal(validatePassword("configured-password"), true);
    assert.equal(verifySessionToken(createSessionToken()), true);
  } finally {
    for (const [key, value] of Object.entries({ NODE_ENV: before.nodeEnv, PORTAL_PASSWORD: before.password, PORTAL_SESSION_SECRET: before.secret })) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
});
