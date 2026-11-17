import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";

// La console est un projet à part : le dépôt a aussi un package-lock.json à sa racine.
const ici = dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  // Un dossier de construction à part pour les essais de bout en bout (playwright.config.ts).
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // Pas de pastille de Next.js sur l'écran, même en local.
  devIndicators: false,
  outputFileTracingRoot: ici,
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    root: ici,
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
