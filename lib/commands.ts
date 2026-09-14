export const promptPresets = [
  "Create a new client setup",
  "Check uploaded data for this month",
  "Run report for one client",
  "Run selected missing reports",
  "Run all active reports",
  "Generate first-month report with zero previous baseline",
  "Show latest report links",
  "Activate or deactivate a client",
] as const;

export type CommandAction =
  | "create-client"
  | "preflight"
  | "run-one"
  | "run-missing"
  | "run-all"
  | "dashboard"
  | "set-active";

export type ConfirmationPlan = {
  action: CommandAction;
  title: string;
  summary: string;
  requiresConfirmation: boolean;
  requiresFirstMonthConfirmation: boolean;
  fields: string[];
  defaults: Record<string, string | boolean>;
};

function includesAny(value: string, terms: string[]) {
  return terms.some((term) => value.includes(term));
}

export function buildConfirmationPlan(input: string): ConfirmationPlan {
  const normalized = input.trim().toLowerCase();
  if (includesAny(normalized, ["create", "setup", "new client"])) {
    return {
      action: "create-client",
      title: "Create client setup",
      summary: "Create a Drive folder, 2026 data Sheet, and master control row.",
      requiresConfirmation: true,
      requiresFirstMonthConfirmation: false,
      fields: ["client_name", "client_key", "active"],
      defaults: { active: false },
    };
  }
  if (includesAny(normalized, ["check", "audit", "uploaded", "preflight"])) {
    return {
      action: "preflight",
      title: "Check uploaded data",
      summary: "Check data readiness and template audit before generating a report.",
      requiresConfirmation: false,
      requiresFirstMonthConfirmation: false,
      fields: ["client_key", "month", "year", "allow_first_month_baseline"],
      defaults: { include_inactive: true },
    };
  }
  if (includesAny(normalized, ["missing"])) {
    return {
      action: "run-missing",
      title: "Run selected missing reports",
      summary: "Generate reports only for selected clients that are missing a report link.",
      requiresConfirmation: true,
      requiresFirstMonthConfirmation: true,
      fields: ["selected_client_keys", "month", "year", "allow_first_month_baseline"],
      defaults: { insights_provider: "auto", include_inactive: true },
    };
  }
  if (includesAny(normalized, ["all active", "run all"])) {
    return {
      action: "run-all",
      title: "Run all active reports",
      summary: "Run audit and generation for every active client.",
      requiresConfirmation: true,
      requiresFirstMonthConfirmation: false,
      fields: ["month", "year"],
      defaults: { insights_provider: "auto" },
    };
  }
  if (includesAny(normalized, ["first-month", "first month", "zero previous"])) {
    return {
      action: "run-one",
      title: "Generate first-month report",
      summary: "Generate one report using a zero previous-period baseline after explicit confirmation.",
      requiresConfirmation: true,
      requiresFirstMonthConfirmation: true,
      fields: ["client_key", "month", "year", "allow_first_month_baseline"],
      defaults: { allow_first_month_baseline: true, include_inactive: true, insights_provider: "auto" },
    };
  }
  if (includesAny(normalized, ["latest", "links", "dashboard", "show"])) {
    return {
      action: "dashboard",
      title: "Show latest report links",
      summary: "Refresh the dashboard with clients, statuses, and latest deck links.",
      requiresConfirmation: false,
      requiresFirstMonthConfirmation: false,
      fields: ["month", "year"],
      defaults: {},
    };
  }
  if (includesAny(normalized, ["activate", "deactivate", "active"])) {
    return {
      action: "set-active",
      title: "Activate or deactivate client",
      summary: "Toggle whether a client is included in active batch runs.",
      requiresConfirmation: true,
      requiresFirstMonthConfirmation: false,
      fields: ["client_key", "active"],
      defaults: { active: true },
    };
  }
  return {
    action: "run-one",
    title: "Run report for one client",
    summary: "Run audit first, then generate one report if audit passes.",
    requiresConfirmation: true,
    requiresFirstMonthConfirmation: false,
    fields: ["client_key", "month", "year", "allow_first_month_baseline"],
    defaults: { insights_provider: "auto", include_inactive: true },
  };
}
