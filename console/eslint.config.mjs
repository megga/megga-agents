import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Ce qui n'est pas du code de la console : essais construits, données locales, captures.
    ".next-e2e/**",
    ".donnees/**",
    "captures/**",
    "test-results/**",
    "playwright-report/**",
  ]),
]);

export default eslintConfig;
