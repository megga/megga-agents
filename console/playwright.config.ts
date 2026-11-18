import { defineConfig, devices } from "@playwright/test";

// Bout en bout : la console, le serveur d'agents (modèle d'essai, sans réseau) et l'atelier d'essai (le vrai atelier sur une
// porte simulée, pour l'admin), chacun sur une base jetable et sur ses propres ports (ni 8100 ni 8198 du développement).
const PYTHON = process.env.AGENTS_PYTHON || "../.venv/bin/python";
const JETON = "jeton-des-essais-e2e";
const JETON_ATELIER = "jeton-atelier-e2e";
const PORT = Number(process.env.E2E_PORT || 3311);
const PORT_ATELIER = 8197;

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
      command: `rm -rf .donnees/e2e-atelier && ${PYTHON} -m uvicorn atelier_essai:app --app-dir agents --host 127.0.0.1 --port ${PORT_ATELIER}`,
      url: `http://127.0.0.1:${PORT_ATELIER}/sante`,
      env: { ATELIER_JETON: JETON_ATELIER, ATELIER_DONNEES: ".donnees/e2e-atelier", ANTHROPIC_API_KEY: "", DEEPSEEK_API_KEY: "" },
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
        ATELIER_URL: `http://127.0.0.1:${PORT_ATELIER}`,
        ATELIER_JETON: JETON_ATELIER,
        NEXT_DIST_DIR: ".next-e2e",
      },
      reuseExistingServer: false,
      timeout: 240_000,
    },
  ],
});
