import { describe, expect, it } from "vitest";
import { SUPERADMIN } from "@/lib/admin/droits";
import { accepterInvitation, creerInvitation } from "@/lib/admin/invitations";
import { ajouterMembre, listerMembres, retirerMembre } from "@/lib/admin/membres";
import { creerRole, lireRole, modifierRole, retirerRole } from "@/lib/admin/roles";
import { TA } from "@/lib/admin/textes";
import { Refus } from "@/lib/agents";
import type { Base } from "@/lib/donnees/base";
import { moteursEssai } from "../moteurs";
import { baseEssai, compte, membre, T0 } from "./aides";

// Les cinq règles qui tenaient à ce que SQLite fait une chose à la fois : chaque essai lance deux opérations ensemble
// (Promise.allSettled), sur chaque moteur d'essai (Postgres seulement si CONSOLE_BASE_ESSAI_URL est posée).

const refusees = (r: PromiseSettledResult<unknown>[]) =>
  r.filter((x): x is PromiseRejectedResult => x.status === "rejected").map((x) => x.reason as unknown);
const reussies = (r: PromiseSettledResult<unknown>[]) => r.filter((x) => x.status === "fulfilled").length;

/** Tient la file des transactions jusqu'à ouvrir() : ce qui est lancé pendant ce temps attend, dans l'ordre où il arrive. */
function bouchon(b: Base): { ouvrir: () => void; fin: Promise<void> } {
  let ouvrir = () => {};
  const porte = new Promise<void>((r) => {
    ouvrir = r;
  });
  return { ouvrir: () => ouvrir(), fin: b.transaction(() => porte) };
}

const attendre = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * Une base d'essai dont le pool Postgres a déjà plusieurs connexions ouvertes : les deux opérations partent chacune sur la
 * sienne, tout de suite, et se croisent vraiment (sans cela, la seconde attendrait l'ouverture d'une connexion).
 */
async function base(moteur: "sqlite" | "postgres"): Promise<Base> {
  const b = await baseEssai(moteur);
  await Promise.all(Array.from({ length: 4 }, () => b.un("SELECT 1 AS n")));
  return b;
}

describe.each(moteursEssai())("deux requêtes à la fois, sous %s", (moteur) => {
  it("une invitation ne sert qu'une fois", async () => {
    const b = await base(moteur);
    const s = await membre(b, { utilisateur: "s", role: SUPERADMIN });
    const { jeton } = await creerInvitation(b, s, { courriel: "n@megga.test", role: "lecture", externe: false, perimetre: "tous", finAcces: null }, T0);
    await compte(b, { id: "n", courriel: "n@megga.test" });
    const r = await Promise.allSettled([
      accepterInvitation(b, jeton, { id: "n", email: "n@megga.test" }, T0),
      accepterInvitation(b, jeton, { id: "n", email: "n@megga.test" }, T0),
    ]);
    expect(reussies(r)).toBe(1);
    expect(refusees(r)).toMatchObject([{ statut: 404, message: TA.invitationInvalide }]);
    expect((await listerMembres(b)).map((m) => m.utilisateur)).toEqual(["n", "s"]);
    expect(await b.tous("SELECT acceptee_par FROM admin_invitation")).toEqual([{ acceptee_par: "n" }]);
  });

  it("il reste un superadmin", async () => {
    const b = await base(moteur);
    const s1 = await membre(b, { utilisateur: "s1", role: SUPERADMIN });
    const s2 = await membre(b, { utilisateur: "s2", role: SUPERADMIN });
    const r = await Promise.allSettled([retirerMembre(b, s1, "s2", T0), retirerMembre(b, s2, "s1", T0)]);
    expect(reussies(r)).toBe(1);
    expect(refusees(r)).toMatchObject([{ statut: 409, message: TA.dernierSuperadmin }]);
    expect((await listerMembres(b)).filter((m) => m.role === SUPERADMIN)).toHaveLength(1);
  });

  it("un seul rôle de ce nom", async () => {
    const b = await base(moteur);
    const s = await membre(b, { utilisateur: "s", role: SUPERADMIN });
    await retirerRole(b, s, "lecture", T0); // le rôle de départ « Lecture » laisse le nom libre
    const r = await Promise.allSettled([
      creerRole(b, s, { nom: "Lecture", droits: ["clients.voir"] }, T0),
      creerRole(b, s, { nom: "lecture", droits: ["clients.voir"] }, T0),
    ]);
    expect(reussies(r)).toBe(1);
    expect(refusees(r)).toMatchObject([{ statut: 409, message: TA.nomPris }]);
    expect(await b.tous("SELECT nom FROM admin_role WHERE lower(nom) = 'lecture'")).toHaveLength(1);
  });

  it("aucun membre sur un rôle retiré", async () => {
    const b = await base(moteur);
    const s = await membre(b, { utilisateur: "s", role: SUPERADMIN });
    const role = await creerRole(b, s, { nom: "Passage", droits: ["clients.voir"] }, T0);
    await compte(b, { id: "n", courriel: "n@megga.test" });
    const r = await Promise.allSettled([
      retirerRole(b, s, role.id, T0),
      ajouterMembre(b, { utilisateur: "n", role: role.id, externe: false, perimetre: "tous", finAcces: null, ajoutePar: "s" }, T0),
    ]);
    expect(reussies(r)).toBe(1);
    for (const e of refusees(r)) expect(e).toBeInstanceOf(Refus);
    const existe = (await lireRole(b, role.id)) !== undefined;
    const porteurs = (await listerMembres(b)).filter((m) => m.role === role.id).map((m) => m.utilisateur);
    // Soit le rôle existe avec son membre, soit aucun des deux.
    expect([existe, porteurs]).toEqual(existe ? [true, ["n"]] : [false, []]);
  });

  it("aucun droit donné d'après un rôle qui vient de changer", async () => {
    const b = await base(moteur);
    const s = await membre(b, { utilisateur: "s", role: SUPERADMIN });
    const gestion = await creerRole(b, s, { nom: "Gestion", droits: ["clients.voir", "couts.voir", "equipe.gerer"] }, T0);
    const couts = await creerRole(b, s, { nom: "Coûts", droits: ["clients.voir", "couts.voir"] }, T0);
    const m = await membre(b, { utilisateur: "m", role: gestion.id }); // son accès, lu avant : il porte encore couts.voir
    const invitation = { courriel: "n@megga.test", role: couts.id, externe: false, perimetre: "tous", finAcces: null };

    // Les deux ensemble, sans ordre imposé : l'invitation passe avant le retrait du droit, ou elle est refusée.
    const libres = await Promise.allSettled([
      modifierRole(b, s, gestion.id, { droits: ["clients.voir", "equipe.gerer"] }, T0),
      creerInvitation(b, m, { ...invitation, courriel: "libre@megga.test" }, T0),
    ]);
    expect(libres[0].status).toBe("fulfilled");
    if (libres[1].status === "rejected") expect(libres[1].reason).toMatchObject({ statut: 403, message: TA.escalade });

    // Le retrait du droit d'abord, l'invitation d'après l'ancien accès ensuite : les deux attendent derrière une même
    // transaction, et passent dans l'ordre où ils sont arrivés.
    await modifierRole(b, s, gestion.id, { droits: ["clients.voir", "couts.voir", "equipe.gerer"] }, T0);
    await b.ecrire("DELETE FROM admin_invitation");
    const tenu = bouchon(b);
    const retrait = modifierRole(b, s, gestion.id, { droits: ["clients.voir", "equipe.gerer"] }, T0);
    await attendre(30); // le retrait attend son tour
    const invite = creerInvitation(b, m, invitation, T0);
    await attendre(30);
    tenu.ouvrir();
    const r = await Promise.allSettled([retrait, invite]);
    await tenu.fin;
    expect(r[0].status).toBe("fulfilled");
    expect(r[1]).toMatchObject({ status: "rejected", reason: { statut: 403, message: TA.escalade } });
    // Jamais d'invitation qui porte un droit que son auteur n'a plus.
    expect(await b.tous("SELECT courriel FROM admin_invitation")).toEqual([]);
  });
});
