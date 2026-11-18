"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Tete } from "@/components/console/tete";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { etatInvitation } from "@/lib/admin/invitations";
import { TA } from "@/lib/admin/textes";
import { authClient } from "@/lib/auth-client";

type Etat = ReturnType<typeof etatInvitation>;

/** La phrase d'un refus de Better Auth à l'inscription. */
function erreurInscription(code: string | undefined): string {
  if (code?.startsWith("USER_ALREADY_EXISTS")) return TA.courrielDejaInscrit;
  if (code === "PASSWORD_TOO_SHORT") return TA.motDePasseCourt;
  return TA.erreurInterne;
}

/** courriel : celui de l'invitation (vide si elle n'est plus valable) ; c'est le seul que l'inscription accepte ici. */
export function Rejoindre({ etat, jeton, courriel }: { etat: Etat; jeton: string; courriel: string }) {
  const router = useRouter();
  const [nom, setNom] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);

  async function rejoindre(): Promise<boolean> {
    const r = await fetch("/api/admin/invitation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jeton }),
    });
    if (r.ok) {
      router.replace("/admin");
      router.refresh();
      return true;
    }
    const corps = await r.json().catch(() => ({}));
    setErreur(corps.erreur || TA.erreurInterne);
    return false;
  }

  async function agir(faire: () => Promise<boolean>) {
    setErreur(null);
    setEnvoi(true);
    try {
      if (!(await faire())) setEnvoi(false);
    } catch {
      setErreur(TA.erreurInterne);
      setEnvoi(false);
    }
  }

  async function inscrire(e: React.FormEvent) {
    e.preventDefault();
    if (motDePasse.length < 8) return setErreur(TA.motDePasseCourt);
    await agir(async () => {
      const { error } = await authClient.signUp.email({ name: nom.trim(), email: courriel, password: motDePasse });
      if (error) {
        setErreur(erreurInscription(error.code));
        return false;
      }
      return rejoindre();
    });
  }

  async function sortir() {
    await authClient.signOut();
    router.refresh(); // la page se relit sans session : créer son compte ou se connecter
  }

  const champ = "h-11 rounded-xl bg-bg px-3.5 text-[15px] text-ink placeholder:text-faint";

  return (
    <main className="flex min-h-dvh items-center justify-center bg-side px-4 py-10">
      <div className="trait w-full max-w-[400px] rounded-[28px] bg-bg px-7 pt-6 pb-7 shadow-doux">
        <Tete couleur={0} yeux={0} className="flotte mx-auto w-[120px]" />
        <h1 className="mt-3 mb-2 text-center text-[24px] font-extrabold tracking-[-0.02em]">{TA.invitationTitre}</h1>

        {etat === "invalide" && <p className="m-0 text-center text-[14.5px] text-muted-ink">{TA.invitationInvalide}</p>}

        {etat !== "invalide" && <p className="mt-0 mb-5 text-center text-[14.5px] break-words text-muted-ink">{TA.invitationPour(courriel)}</p>}

        {etat === "rejoindre" && (
          <Button type="button" disabled={envoi} onClick={() => agir(rejoindre)} className="h-11 w-full rounded-full text-[15px] font-bold">
            {TA.rejoindre}
          </Button>
        )}

        {etat === "autre_courriel" && (
          <>
            <p className="mt-0 mb-4 text-center text-[14px] font-semibold text-ink">{TA.autreCourriel}</p>
            <Button type="button" variant="outline" onClick={sortir} className="h-11 w-full rounded-full text-[14.5px] font-semibold">
              {TA.seDeconnecter}
            </Button>
          </>
        )}

        {etat === "sans_session" && (
          <>
            <form onSubmit={inscrire} className="flex flex-col gap-3.5">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="nom" className="text-[13px] font-semibold text-muted-ink">{TA.votreNom}</Label>
                <Input id="nom" required maxLength={120} autoComplete="name" value={nom} onChange={(e) => setNom(e.target.value)} className={champ} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="courriel" className="text-[13px] font-semibold text-muted-ink">{TA.courriel}</Label>
                <Input id="courriel" type="email" readOnly value={courriel} className={champ + " bg-side text-muted-ink"} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="mot-de-passe" className="text-[13px] font-semibold text-muted-ink">{TA.motDePasse}</Label>
                <Input
                  id="mot-de-passe"
                  type="password"
                  required
                  autoComplete="new-password"
                  value={motDePasse}
                  onChange={(e) => setMotDePasse(e.target.value)}
                  className={champ}
                />
              </div>
              <Button type="submit" disabled={envoi} className="mt-1 h-11 rounded-full text-[15px] font-bold">
                {TA.creerEtRejoindre}
              </Button>
            </form>
            <p className="mt-5 mb-0 text-center text-[13.5px] text-muted-ink">
              {TA.dejaUnCompte}{" "}
              <Link href={`/connexion?retour=/admin/invitation/${jeton}`} className="font-bold text-ink hover:underline">
                {TA.seConnecter}
              </Link>
            </p>
          </>
        )}

        {erreur && (
          <p role="alert" className="mt-4 mb-0 text-center text-[13.5px] font-semibold text-marque">
            {erreur}
          </p>
        )}
      </div>
    </main>
  );
}
