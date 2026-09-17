import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  outputFileTracingIncludes: {
    "/api/chat": ["./data/gita-index.json", "./data/gita-verses.json"],
  },
};

export default nextConfig;
