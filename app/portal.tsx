"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { promptPresets, type ConfirmationPlan } from "@/lib/commands";

type ClientRow = {
  client_name: string;
  client_key: string;
  active: boolean;
  latest_report_url?: string;
};

type Dashboard = {
  status: string;
  period: string;
  prev_period: string;
  clients: ClientRow[];
  missing_clients: ClientRow[];
};

type Status = "Idle" | "Pending" | "Success" | "Failed";

const monthNames = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

function defaultReportPeriod() {
  const now = new Date();
  const previous = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  return { month: monthNames[previous.getMonth()], year: String(previous.getFullYear()) };
}

export default function Portal() {
  const defaults = useMemo(() => defaultReportPeriod(), []);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [prompt, setPrompt] = useState("Run report for one client");
  const [plan, setPlan] = useState<ConfirmationPlan | null>(null);
  const [payload, setPayload] = useState<Record<string, string | boolean | string[]>>({
    month: defaults.month,
    year: defaults.year,
    insights_provider: "auto",
    include_inactive: true,
  });
  const [status, setStatus] = useState<Status>("Idle");
  const [message, setMessage] = useState("");
  const [result, setResult] = useState<unknown>(null);

  const refreshDashboard = useCallback(async () => {
    const response = await fetch(`/api/dashboard?month=${payload.month || defaults.month}&year=${payload.year || defaults.year}`);
    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }
    const data = (await response.json()) as Dashboard;
    setDashboard(data);
  }, [defaults.month, defaults.year, payload.month, payload.year]);

  useEffect(() => {
    refreshDashboard().catch((error) => setMessage(String(error)));
  }, [refreshDashboard]);

  async function buildPlan(selectedPrompt = prompt) {
    setStatus("Pending");
    setMessage("");
    setResult(null);
    const response = await fetch("/api/chat-command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: selectedPrompt }),
    });
    const data = await response.json();
    if (!response.ok) {
      setStatus("Failed");
      setMessage(data.error || "Could not prepare command.");
      return;
    }
    setPlan(data.plan);
    setPayload((current) => ({ ...data.plan.defaults, month: defaults.month, year: defaults.year, ...current }));
    setStatus("Idle");
  }

  async function execute(event: FormEvent) {
    event.preventDefault();
    if (!plan) {
      await buildPlan();
      return;
    }
    if (payload.allow_first_month_baseline && !payload.confirm_first_month_baseline) {
      setStatus("Failed");
      setMessage("Confirm the first-month baseline warning before running.");
      return;
    }
    setStatus("Pending");
    setMessage("");
    setResult(null);
    const response = await fetch("/api/execute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: plan.action, payload }),
    });
    const data = await response.json();
    if (!response.ok || data.status === "error") {
      setStatus("Failed");
      setMessage(data.error || "Action failed.");
      setResult(data);
      return;
    }
    setStatus("Success");
    setMessage(plan.action === "dashboard" ? "Dashboard refreshed." : "Action completed.");
    setResult(data);
    await refreshDashboard();
  }

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/login";
  }

  function setField(name: string, value: string | boolean | string[]) {
    setPayload((current) => ({ ...current, [name]: value }));
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>MT Report Ops</h1>
          <p>{dashboard ? `${dashboard.period} reports, comparing ${dashboard.prev_period}` : "Loading dashboard..."}</p>
        </div>
        <div className="topbar-actions">
          <Link href="/benchmarks">Country benchmarks ↗</Link>
          <button className="ghost-button" type="button" onClick={() => void logout()}>Log out</button>
        </div>
      </header>

      <section className="workspace">
        <section className="primary-panel">
          <div className="panel-heading">
            <h2>Chat Command</h2>
            <span className={`status-pill ${status.toLowerCase()}`}>{status}</span>
          </div>

          <div className="preset-grid">
            {promptPresets.map((item) => (
              <button
                key={item}
                className="preset-button"
                type="button"
                onClick={() => {
                  setPrompt(item);
                  void buildPlan(item);
                }}
              >
                {item}
              </button>
            ))}
          </div>

          <form className="command-form" onSubmit={execute}>
            <label>
              Command
              <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={3} />
            </label>
            <div className="actions-row">
              <button type="button" onClick={() => void buildPlan()}>Prepare</button>
              <button type="submit" disabled={status === "Pending"}>{plan ? "Execute" : "Prepare"}</button>
            </div>

            {plan ? (
              <div className="confirmation-panel">
                <h3>{plan.title}</h3>
                <p>{plan.summary}</p>
                <DynamicFields
                  plan={plan}
                  payload={payload}
                  clients={dashboard?.clients || []}
                  missingClients={dashboard?.missing_clients || []}
                  setField={setField}
                />
              </div>
            ) : null}
          </form>

          {message ? <p className={status === "Failed" ? "error-text" : "success-text"}>{message}</p> : null}
          {result ? <ResultBlock result={result} /> : null}
        </section>

        <aside className="secondary-panel">
          <div className="panel-heading">
            <h2>Dashboard</h2>
            <button className="ghost-button" type="button" onClick={() => void refreshDashboard()}>Refresh</button>
          </div>
          <div className="metric-row">
            <Metric label="Clients" value={String(dashboard?.clients.length || 0)} />
            <Metric label="Missing" value={String(dashboard?.missing_clients.length || 0)} />
          </div>
          <div className="client-list">
            {(dashboard?.clients || []).map((client) => (
              <div className="client-row" key={client.client_key}>
                <div>
                  <strong>{client.client_name}</strong>
                  <span>{client.client_key} · {client.active ? "active" : "inactive"}</span>
                </div>
                {client.latest_report_url ? (
                  <a href={client.latest_report_url} target="_blank" rel="noreferrer">Open</a>
                ) : (
                  <span className="muted">No link</span>
                )}
              </div>
            ))}
          </div>
        </aside>
      </section>
    </main>
  );
}

function DynamicFields({
  plan,
  payload,
  clients,
  missingClients,
  setField,
}: {
  plan: ConfirmationPlan;
  payload: Record<string, string | boolean | string[]>;
  clients: ClientRow[];
  missingClients: ClientRow[];
  setField: (name: string, value: string | boolean | string[]) => void;
}) {
  const selected = Array.isArray(payload.selected_client_keys) ? payload.selected_client_keys : [];
  return (
    <div className="field-grid">
      {plan.fields.includes("client_name") ? (
        <label>
          Client name
          <input value={String(payload.client_name || "")} onChange={(event) => setField("client_name", event.target.value)} />
        </label>
      ) : null}
      {plan.fields.includes("client_key") ? (
        <label>
          Client
          <select value={String(payload.client_key || "")} onChange={(event) => setField("client_key", event.target.value)}>
            <option value="">Select client</option>
            {clients.map((client) => (
              <option key={client.client_key} value={client.client_key}>{client.client_name}</option>
            ))}
          </select>
        </label>
      ) : null}
      {plan.fields.includes("month") ? (
        <label>
          Month
          <select value={String(payload.month || "")} onChange={(event) => setField("month", event.target.value)}>
            {monthNames.map((month) => <option key={month} value={month}>{month}</option>)}
          </select>
        </label>
      ) : null}
      {plan.fields.includes("year") ? (
        <label>
          Year
          <input value={String(payload.year || "")} onChange={(event) => setField("year", event.target.value)} />
        </label>
      ) : null}
      {plan.fields.includes("active") ? (
        <label className="check-label">
          <input
            type="checkbox"
            checked={Boolean(payload.active)}
            onChange={(event) => setField("active", event.target.checked)}
          />
          Active
        </label>
      ) : null}
      {plan.fields.includes("selected_client_keys") ? (
        <div className="span-all">
          <strong>Missing clients</strong>
          <div className="check-list">
            {missingClients.map((client) => (
              <label key={client.client_key} className="check-label">
                <input
                  type="checkbox"
                  checked={selected.includes(client.client_key)}
                  onChange={(event) => {
                    const next = event.target.checked
                      ? [...selected, client.client_key]
                      : selected.filter((key) => key !== client.client_key);
                    setField("selected_client_keys", next);
                  }}
                />
                {client.client_name}
              </label>
            ))}
            {!missingClients.length ? <p className="muted">No missing clients for the selected period.</p> : null}
          </div>
        </div>
      ) : null}
      {plan.fields.includes("allow_first_month_baseline") ? (
        <div className="span-all warning-box">
          <label className="check-label">
            <input
              type="checkbox"
              checked={Boolean(payload.allow_first_month_baseline)}
              onChange={(event) => setField("allow_first_month_baseline", event.target.checked)}
            />
            Allow zero previous-period baseline
          </label>
          {payload.allow_first_month_baseline ? (
            <label className="check-label">
              <input
                type="checkbox"
                checked={Boolean(payload.confirm_first_month_baseline)}
                onChange={(event) => setField("confirm_first_month_baseline", event.target.checked)}
              />
              I confirm current-month data is complete and previous-month rows do not exist.
            </label>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ResultBlock({ result }: { result: unknown }) {
  return (
    <pre className="result-block">{JSON.stringify(result, null, 2)}</pre>
  );
}
