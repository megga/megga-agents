import { defineConfig, devices } from "@playwright/test";

// Bout en bout : la console et le serveur d'agents (modèle d'essai, sans réseau), sur une base jetable.
const PYTHON = process.env.AGENTS_PYTHON || "../.venv/bin/python";
const JETON = "jeton-des-essais-e2e";
const PORT = Number(process.env.E2E_PORT || 3311);

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: `http://localhost:${PORT}`, locale: "fr-FR", viewport: { width: 1440, height: 900 } },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
  webServer: [
    {
      command: `rm -rf .donnees/e2e-agents && ${PYTHON} -m uvicorn serveur:app --app-dir agents --host 127.0.0.1 --port 8199`,
      url: "http://127.0.0.1:8199/sante",
      env: { AGENTS_JETON: JETON, AGENTS_DONNEES: ".donnees/e2e-agents", ANTHROPIC_API_KEY: "" },
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `rm -f .donnees/e2e.sqlite* && npx next build && npx next start -p ${PORT}`,
      url: `http://localhost:${PORT}/connexion`,
      env: {
        CONSOLE_BASE: ".donnees/e2e.sqlite",
        BETTER_AUTH_SECRET: "secret-des-essais-e2e-qui-ne-sert-qu-ici",
        BETTER_AUTH_URL: `http://localhost:${PORT}`,
        AGENTS_URL: "http://127.0.0.1:8199",
        AGENTS_JETON: JETON,
        NEXT_DIST_DIR: ".next-e2e",
      },
      reuseExistingServer: false,
      timeout: 240_000,
    },
  ],
});
