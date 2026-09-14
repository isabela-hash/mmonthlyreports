/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  outputFileTracingIncludes: {
    "/api/**/*": [
      "./.python_packages/**/*",
      "./tools/**/*",
      "./workflows/**/*",
      "./requirements.txt",
    ],
  },
};

export default nextConfig;
