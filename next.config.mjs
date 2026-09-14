import path from "node:path";

const root = process.cwd();
const runtimeFiles = [".python_packages/**/*", "tools/**/*", "workflows/**/*", "requirements.txt"].map(file => path.join(root, file));
const privateFiles = ["data/**/*", "output/**/*", ".env*", "token*.pickle", "credentials.json", "*service-account*.json", ".venv/**/*", "tests/**/*", ".git/**/*"];

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  outputFileTracingExcludes: { "/**": privateFiles },
  outputFileTracingIncludes: {
    "/benchmarks": runtimeFiles,
    "/api/**/*": runtimeFiles,
  },
};

export default nextConfig;
