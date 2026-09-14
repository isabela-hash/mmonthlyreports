import Link from "next/link";
import { redirect } from "next/navigation";
import { isAuthenticated } from "@/lib/auth";
import { runReportOps } from "@/lib/python";
import AccessButton from "./access-button";
import styles from "./report.module.css";
export const dynamic = "force-dynamic";
export const metadata = { title: "Country benchmark archive", robots: { index: false, follow: false } };
export default async function Page() {
  if (!await isAuthenticated()) redirect("/login");
  let reports: string[] = [], unavailable = false;
  try { reports = (await runReportOps<{ reports: string[] }>("benchmark-list")).reports; } catch { unavailable = true; }
  return <main className={styles.page}><Link href="/">← Reports portal</Link><h1>Country benchmarks</h1><p>Monthly copies · Six complete months · USD</p>
    {unavailable ? <p role="status">Snapshot storage is not connected yet. Configure the private Drive integration to load verified reports.</p> : reports.length ? <ul>{reports.map(id => <li key={id}>{id} — <Link href={`/benchmarks/${id}/private`}>Private report</Link> · <Link href={`/benchmarks/${id}/share`}>Shareable report</Link> · <AccessButton id={id} /></li>)}</ul> : <p>No verified snapshot has been published yet.</p>}
  </main>;
}
