import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Un dossier de construction à part pour les essais de bout en bout (playwright.config.ts).
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // Pas de pastille de Next.js sur l'écran, même en local.
  devIndicators: false,
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
