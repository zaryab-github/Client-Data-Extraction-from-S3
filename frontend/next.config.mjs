/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Produce a self-contained server build for a slim production Docker image.
  output: "standalone",
  // No hardcoded hosts/URLs here — the app reads NEXT_PUBLIC_* values.
  // NEXT_PUBLIC_* are inlined at BUILD time, so the frontend image is rebuilt
  // when the API URL changes (passed as a build arg in docker-compose.prod.yml).
};

export default nextConfig;
