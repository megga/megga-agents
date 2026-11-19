import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Le lint typé : une promesse laissée sans attente, une promesse dans une condition, un await sur ce qui n'en est pas une.
  // Toute la console parle à la base en asynchrone (src/lib/donnees) : un oubli d'await y serait une écriture perdue.
  {
    files: ["src/**/*.{ts,tsx}", "scripts/**/*.ts", "tests/**/*.ts"],
    languageOptions: { parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname } },
    rules: {
      "@typescript-eslint/no-floating-promises": "error",
      // Un gestionnaire d'événement async dans le JSX (onClick, onSubmit) reste permis : React n'attend pas sa promesse.
      "@typescript-eslint/no-misused-promises": ["error", { checksVoidReturn: { attributes: false } }],
      "@typescript-eslint/await-thenable": "error",
    },
  },
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
