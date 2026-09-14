import { redirect } from "next/navigation";
import { isAuthenticated } from "@/lib/auth";
import GeoPerformance from "./geo-performance";

export default async function AlphaGeoPerformancePage() {
  if (!(await isAuthenticated())) {
    redirect("/login");
  }
  return <GeoPerformance />;
}
