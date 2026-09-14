import assert from "node:assert/strict";
import { test } from "node:test";
import { buildConfirmationPlan } from "../../lib/commands";

test("buildConfirmationPlan maps first-month prompts to confirmed run action", () => {
  const plan = buildConfirmationPlan("Generate first-month report with zero previous baseline");

  assert.equal(plan.action, "run-one");
  assert.equal(plan.requiresFirstMonthConfirmation, true);
  assert.equal(plan.defaults.allow_first_month_baseline, true);
});

test("buildConfirmationPlan maps missing report prompts to selected missing run action", () => {
  const plan = buildConfirmationPlan("Run selected missing reports");

  assert.equal(plan.action, "run-missing");
  assert.ok(plan.fields.includes("selected_client_keys"));
});

test("buildConfirmationPlan defaults unknown commands to one report run", () => {
  const plan = buildConfirmationPlan("please do the Terminal report");

  assert.equal(plan.action, "run-one");
  assert.equal(plan.defaults.insights_provider, "auto");
});
