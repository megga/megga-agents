import { defineConfig, devices } from "@playwright/test";

// Bout en bout : la console, le serveur d'agents (modèle d'essai, sans réseau) et l'atelier d'essai (le vrai atelier sur une
// porte simulée, pour l'admin), chacun sur une base jetable et sur ses propres ports (ni 8100 ni 8198 du développement).
// La console prend un fichier SQLite neuf, ou Postgres quand CONSOLE_BASE_URL est posée (la CI : une base neuve à chaque fois).
const PYTHON = process.env.AGENTS_PYTHON || "../.venv/bin/python";
const JETON = "jeton-des-essais-e2e";
const JETON_ATELIER = "jeton-atelier-e2e";
const PORT = Number(process.env.E2E_PORT || 3311);
const PORT_ATELIER = 8197;

// Les parcours inscrivent des comptes et invitent un superadmin au mot de passe écrit dans e2e/compte.ts : jamais sur une
// base qui n'est pas locale (la production, par une CONSOLE_BASE_URL restée exportée dans le terminal).
const BASE_POSTGRES = process.env.CONSOLE_BASE_URL;
if (BASE_POSTGRES) {
  let hote = "";
  try {
    hote = new URL(BASE_POSTGRES).hostname;
  } catch {
    // illisible : refusée plus bas
  }
  if (!["localhost", "127.0.0.1", "[::1]", "::1"].includes(hote)) {
    throw new Error(
      "CONSOLE_BASE_URL nomme une base qui n'est pas sur cette machine : les parcours ne jouent que sur une base locale. " +
        "Retirez-la (unset CONSOLE_BASE_URL) ou nommez un Postgres local.",
    );
  }
}

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
        CONSOLE_INSCRIPTION: "ouverte",
        AGENTS_URL: "http://127.0.0.1:8199",
        AGENTS_JETON: JETON,
        ATELIER_URL: `http://127.0.0.1:${PORT_ATELIER}`,
        ATELIER_JETON: JETON_ATELIER,
        NEXT_DIST_DIR: ".next-e2e",
        ...(BASE_POSTGRES ? { CONSOLE_BASE_URL: BASE_POSTGRES } : {}),
      },
      reuseExistingServer: false,
      timeout: 240_000,
    },
  ],
});
