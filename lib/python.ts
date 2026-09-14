import { spawn } from "node:child_process";
import path from "node:path";

export type PythonResult<T = unknown> = T & { status?: string };

const ROOT = process.cwd();
const PYTHON = process.env.REPORT_PORTAL_PYTHON || "python3";
const PYTHON_PACKAGES = repoPath(".python_packages");

export function runReportOps<T = PythonResult>(command: string, payload: Record<string, unknown> = {}) {
  return new Promise<T>((resolve, reject) => {
    const child = spawn(PYTHON, ["tools/report_ops_cli.py", command], {
      cwd: ROOT,
      env: {
        ...process.env,
        PYTHONPATH: [PYTHON_PACKAGES, process.env.PYTHONPATH].filter(Boolean).join(":"),
      },
      stdio: ["pipe", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (code) => {
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

export function repoPath(...parts: string[]) {
  return path.join(ROOT, ...parts);
}
