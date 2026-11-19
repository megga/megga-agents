import { T } from "@/lib/textes";
import { creer, lister, Refus, retirer } from "@/lib/agents";
import { sessionDe } from "@/lib/auth";
import { pret } from "@/lib/base";
import { inscrire } from "@/lib/serveur-agents";

export async function GET(requete: Request) {
  const s = await sessionDe(requete);
  if (!s) return Response.json({ erreur: T.connectezVous }, { status: 401 });
  return Response.json({ agents: await lister(await pret(), s.user.id) });
}

export async function POST(requete: Request) {
  const s = await sessionDe(requete);
  if (!s) return Response.json({ erreur: T.connectezVous }, { status: 401 });
  let agent;
  try {
    agent = await creer(await pret(), s.user.id, await requete.json().catch(() => null));
  } catch (e) {
    if (e instanceof Refus) return Response.json({ erreur: e.message }, { status: e.statut });
    throw e;
  }
  try {
    await inscrire(agent.id, { prenom: agent.prenom, metier: agent.metier, entreprise: s.user.name || "Votre entreprise" });
  } catch (e) {
    await retirer(await pret(), s.user.id, agent.id);
    console.error("création d'agent :", e);
    return Response.json({ erreur: T.serviceIndisponible }, { status: 502 });
  }
  return Response.json({ agent }, { status: 201 });
}
