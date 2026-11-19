import { describe, expect, it } from "vitest";
import { TA } from "@/lib/admin/textes";
import { navigateurDe } from "@/lib/navigateur";

// Le navigateur et le système d'un appareil connecté, lus dans son agent utilisateur : quelques cas courants, sinon inconnu.

const AGENTS: [string, string][] = [
  ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36", "Chrome sur macOS"],
  ["Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1", "Safari sur iPhone"],
  ["Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0", "Firefox sur Windows"],
  ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0", "Edge sur Windows"],
  ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15", "Safari sur macOS"],
  ["Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36", "Chrome sur Android"],
  ["Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/131.0.6778.73 Mobile/15E148 Safari/604.1", "Chrome sur iPhone"],
  ["Mozilla/5.0 (iPad; CPU OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Mobile/15E148 Safari/604.1", "Safari sur iPad"],
  ["Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0", "Firefox sur Linux"],
];

describe("le navigateur d'un appareil", () => {
  for (const [agent, attendu] of AGENTS) {
    it(attendu, () => expect(navigateurDe(agent)).toBe(attendu));
  }

  it("inconnu sans agent ou pour un agent qu'il ne reconnaît pas", () => {
    expect(navigateurDe(null)).toBe(TA.navigateurInconnu);
    expect(navigateurDe("")).toBe(TA.navigateurInconnu);
    expect(navigateurDe("curl/8.7.1")).toBe(TA.navigateurInconnu);
    expect(navigateurDe("Mozilla/5.0 Essai")).toBe(TA.navigateurInconnu);
  });

  it("le navigateur seul quand le système ne se lit pas", () => {
    expect(navigateurDe("Mozilla/5.0 (Inconnu) Gecko/20100101 Firefox/133.0")).toBe("Firefox");
  });
});
