const API_TARGET = (process.env.NEXT_PUBLIC_API_URL || process.env.API_PROXY_TARGET || "http://127.0.0.1:8000").replace(/\/$/, "");

/** @type {import('next').NextConfig} */
const nextConfig = {
  images: { unoptimized: true },
  experimental: {
    optimizePackageImports: ["lucide-react", "recharts"],
  },
  async rewrites() {
    return [
      { source: "/api/rbac/:path*", destination: `${API_TARGET}/api/rbac/:path*` },
      { source: "/api/runtime/:path*", destination: `${API_TARGET}/admin/runtime/:path*` },
      { source: "/api/sandbox-policies/:path*", destination: `${API_TARGET}/admin/sandbox-policies/:path*` },
      { source: "/api/admin/:path*", destination: `${API_TARGET}/api/admin/:path*` },
      { source: "/api/developer/:path*", destination: `${API_TARGET}/developers/:path*` },
      { source: "/api/marketplace/:path*", destination: `${API_TARGET}/agent-marketplace/:path*` },
      { source: "/api/imports/:path*", destination: `${API_TARGET}/imports/:path*` },
      { source: "/api/import/:path*", destination: `${API_TARGET}/imports/:path*` },
    ];
  },
};

module.exports = nextConfig;
