/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "res.cloudinary.com" },
    ],
  },
  async rewrites() {
    // In dev, proxy /api/backend/* to FastAPI so cookies stay same-site.
    return [
      {
        source: "/api/backend/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1/:path*`,
      },
    ];
  },
  async headers() {
    // Google Identity Services needs the page origin in the Referer and needs
    // to keep a handle on its sign-in popup. Next's defaults are usually
    // enough, but setting them explicitly avoids "origin is not allowed" and
    // blank-popup regressions when deploy configs add stricter headers.
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Cross-Origin-Opener-Policy", value: "same-origin-allow-popups" },
        ],
      },
    ];
  },
};

export default nextConfig;
