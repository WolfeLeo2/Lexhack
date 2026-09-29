import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Uploaded filings go through a server action (app/check/actions.ts). Vercel caps function bodies at ~4.5 MB,
  // so the page accepts files up to 4 MB; the API itself takes 10 MB.
  experimental: { serverActions: { bodySizeLimit: "4.5mb" } },
};

export default nextConfig;
