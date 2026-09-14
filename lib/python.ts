import { spawn } from "node:child_process";
import path from "node:path";

export type PythonResult<T = unknown> = T & { status?: string };

const ROOT = path.join(/* turbopackIgnore: true */ process.cwd());
const PYTHON = process.env.REPORT_PORTAL_PYTHON || "python3";
const PYTHON_PACKAGES = path.join(/* turbopackIgnore: true */ process.cwd(), ".python_packages");

export function runReportOps<T = PythonResult>(command: string, payload: Record<string, unknown> = {}) {
  return new Promise<T>((resolve, reject) => {
    const child = spawn(/* turbopackIgnore: true */ PYTHON, ["tools/report_ops_cli.py", command], {
      cwd: ROOT,
      env: {
        ...process.env,
        PYTHONPATH: [PYTHON_PACKAGES, process.env.PYTHONPATH].filter(Boolean).join(":"),
      },
      stdio: ["pipe", "pipe", "pipe"],
    });
    const timer = setTimeout(() => { child.kill("SIGTERM"); reject(new Error("Report operation timed out")); }, command.startsWith("benchmark-") ? 55_000 : 600_000);
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", (error) => { clearTimeout(timer); reject(error); });
    child.on("close", (code) => {
      clearTimeout(timer);
      const raw = code === 0 ? stdout : stderr || stdout;
      let parsed: unknown;
      try {
        parsed = raw.trim() ? JSON.parse(raw) : {};
      } catch {
        parsed = { status: "error", error: raw.trim() || `Python command failed with exit code ${code}` };
      }
      if (code !== 0) {
        const message = typeof parsed === "object" && parsed && "error" in parsed
          ? String((parsed as { error: unknown }).error)
          : `Python command failed with exit code ${code}`;
        reject(new Error(message));
        return;
      }
      resolve(parsed as T);
    });
    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}
