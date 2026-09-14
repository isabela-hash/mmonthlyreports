"use client";
import { useState } from "react";
export default function AccessButton({ id }: { id: string }) {
  const [message, setMessage] = useState("");
  return <span><button onClick={async () => {
    if (message) { setMessage(""); return; }
    try { const response = await fetch(`/api/benchmarks/${id}/passwords`, { method: "POST" }); const data = await response.json(); setMessage(response.ok ? `Private: ${data.private} · Shareable: ${data.share}` : data.error); }
    catch { setMessage("Unable to retrieve passwords"); }
  }}>{message ? "Hide passwords" : "Show report passwords"}</button>{message && <span role="status"> {message}</span>}</span>;
}
