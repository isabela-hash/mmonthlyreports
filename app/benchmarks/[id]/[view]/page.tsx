import { notFound } from "next/navigation";
import { validScope } from "@/lib/benchmark-auth";
import BenchmarkReport from "../../report";
export const dynamic = "force-dynamic";
export const metadata = { title: "Country benchmarks | Modernized", robots: { index: false, follow: false } };
export default async function Page({ params }: { params: Promise<{ id: string; view: string }> }) {
  const { id, view } = await params;
  if (!validScope(id, view)) notFound();
  return <BenchmarkReport id={id} view={view} />;
}
