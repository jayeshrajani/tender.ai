import type { NextConfig } from "next";

const apiUrl = process.env.TENDEROS_API_INTERNAL_URL ?? "http://127.0.0.1:8010";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  devIndicators: { position: "bottom-right" },
  async rewrites() {
    // Same-origin proxy so the httpOnly session cookie never needs cross-site CORS.
    return [
      { source: "/api/:path*", destination: `${apiUrl}/api/:path*` },
      { source: "/health", destination: `${apiUrl}/health` },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
