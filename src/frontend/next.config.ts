import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Proxy /api/* → cerebro-api:8001 server-side (no CORS, no hardcoded IPs)
  async rewrites() {
    const apiUrl = process.env.CEREBRO_API_URL || "http://cerebro-api:8001";
    return [
      { source: "/api/:path*", destination: `${apiUrl}/:path*` },
    ];
  },
};

export default nextConfig;
