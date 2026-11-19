import { TA } from "./admin/textes";

// Le navigateur et le système d'un appareil connecté, lus dans son agent utilisateur (la colonne userAgent d'une session de
// Better Auth) : quelques cas courants, dans l'ordre où ils se reconnaissent (Edge et Opera se disent aussi Chrome, Chrome se
// dit aussi Safari). Sinon, navigateur inconnu ; un système qui ne se lit pas, le navigateur seul.

const NAVIGATEURS: [RegExp, string][] = [
  [/\bEdg(e|A|iOS)?\//, "Edge"],
  [/\b(OPR|Opera)\//, "Opera"],
  [/\b(Firefox|FxiOS)\//, "Firefox"],
  [/\b(Chrome|CriOS|Chromium)\//, "Chrome"],
  [/\bVersion\/[\d.]+.*\bSafari\//, "Safari"],
];

const SYSTEMES: [RegExp, string][] = [
  [/\biPhone\b/, "iPhone"],
  [/\biPad\b/, "iPad"],
  [/\bAndroid\b/, "Android"],
  [/\bWindows\b/, "Windows"],
  [/\bCrOS\b/, "ChromeOS"],
  [/\bMac OS X\b|\bMacintosh\b/, "macOS"],
  [/\bLinux\b/, "Linux"],
];

const premier = (agent: string, liste: [RegExp, string][]) => liste.find(([motif]) => motif.test(agent))?.[1];

export function navigateurDe(agent: string | null): string {
  const navigateur = agent ? premier(agent, NAVIGATEURS) : undefined;
  if (!agent || !navigateur) return TA.navigateurInconnu;
  const systeme = premier(agent, SYSTEMES);
  return systeme ? TA.navigateurSur(navigateur, systeme) : navigateur;
}
