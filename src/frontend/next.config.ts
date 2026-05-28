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
  // Security headers — defense in depth.
  // Aplicados a TODA respuesta del frontend (Tailscale Funnel termina TLS
  // en el sidecar y proxia plain HTTP a cerebro-web; los headers viajan
  // de vuelta al cliente sobre HTTPS).
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          {
            // 2 años; preload para que browsers cargen HSTS desde el built-in list.
            key: "Strict-Transport-Security",
            value: "max-age=63072000; includeSubDomains",
          },
          {
            // El frontend nunca debe embeberse en iframe -> previene clickjacking.
            key: "X-Frame-Options",
            value: "DENY",
          },
          {
            // No MIME sniffing en respuestas con Content-Type explicito.
            key: "X-Content-Type-Options",
            value: "nosniff",
          },
          {
            // No filtrar URL completa al navegar a otros dominios.
            key: "Referrer-Policy",
            value: "strict-origin-when-cross-origin",
          },
          {
            // Bloquea capacidades que la app NO usa.
            key: "Permissions-Policy",
            value:
              "camera=(), microphone=(), geolocation=(), payment=(), usb=(), bluetooth=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
