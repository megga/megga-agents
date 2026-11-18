"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Tete } from "@/components/console/tete";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authClient } from "@/lib/auth-client";
import { T } from "@/lib/textes";

export { retourSur } from "./retour";

export function messageErreur(code: string | undefined): string {
  if (!code) return T.erreurGenerale;
  if (code === "INVALID_EMAIL_OR_PASSWORD" || code === "INVALID_EMAIL" || code === "INVALID_PASSWORD") return T.erreurIdentifiants;
  if (code.startsWith("USER_ALREADY_EXISTS")) return T.erreurDejaInscrit;
  if (code === "PASSWORD_TOO_SHORT") return T.erreurMotDePasse;
  return T.erreurGenerale;
}

/** retour : déjà passé par retourSur (page.tsx) ; on y va après la connexion. */
export function Connexion({ fournisseurs, retour }: { fournisseurs: ("google" | "microsoft")[]; retour: string }) {
  const [mode, setMode] = useState<"connexion" | "inscription">("connexion");
  const [entreprise, setEntreprise] = useState("");
  const [courriel, setCourriel] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);
  const inscription = mode === "inscription";
  const router = useRouter();

  async function valider(e: React.FormEvent) {
    e.preventDefault();
    setErreur(null);
    if (inscription && motDePasse.length < 8) return setErreur(T.erreurMotDePasse);
    setEnvoi(true);
    const { error } = inscription
      ? await authClient.signUp.email({ name: entreprise.trim(), email: courriel.trim(), password: motDePasse })
      : await authClient.signIn.email({ email: courriel.trim(), password: motDePasse });
    if (error) {
      setErreur(messageErreur(error.code));
      setEnvoi(false);
      return;
    }
    router.replace(retour);
    router.refresh();
  }

  const champ = "h-11 rounded-xl bg-bg px-3.5 text-[15px] text-ink placeholder:text-faint";

  return (
    <main className="flex min-h-dvh items-center justify-center bg-side px-4 py-10">
      <div className="trait w-full max-w-[400px] rounded-[28px] bg-bg px-7 pt-6 pb-7 shadow-doux">
        <Tete couleur={0} yeux={0} className="flotte mx-auto w-[120px]" />
        <h1 className="mt-3 mb-5 text-center text-[24px] font-extrabold tracking-[-0.02em]">{inscription ? T.inscriptionTitre : T.connexionTitre}</h1>

        {fournisseurs.length > 0 && (
          <>
            <div className="flex flex-col gap-2">
              {fournisseurs.includes("google") && (
                <Button type="button" variant="outline" className="h-11 rounded-full text-[14.5px] font-semibold" onClick={() => authClient.signIn.social({ provider: "google", callbackURL: retour })}>
                  {T.avecGoogle}
                </Button>
              )}
              {fournisseurs.includes("microsoft") && (
                <Button type="button" variant="outline" className="h-11 rounded-full text-[14.5px] font-semibold" onClick={() => authClient.signIn.social({ provider: "microsoft", callbackURL: retour })}>
                  {T.avecMicrosoft}
                </Button>
              )}
            </div>
            <div className="my-4 flex items-center gap-3 text-[12.5px] text-faint">
              <span className="h-(--fin) flex-1 bg-trait" />
              {T.ou}
              <span className="h-(--fin) flex-1 bg-trait" />
            </div>
          </>
        )}

        <form onSubmit={valider} className="flex flex-col gap-3.5">
          {inscription && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="entreprise" className="text-[13px] font-semibold text-muted-ink">{T.entreprise}</Label>
              <Input id="entreprise" required maxLength={120} autoComplete="organization" value={entreprise} onChange={(e) => setEntreprise(e.target.value)} className={champ} />
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="courriel" className="text-[13px] font-semibold text-muted-ink">{T.courriel}</Label>
            <Input id="courriel" type="email" required autoComplete="email" value={courriel} onChange={(e) => setCourriel(e.target.value)} className={champ} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="mot-de-passe" className="text-[13px] font-semibold text-muted-ink">{T.motDePasse}</Label>
            <Input
              id="mot-de-passe"
              type="password"
              required
              autoComplete={inscription ? "new-password" : "current-password"}
              value={motDePasse}
              onChange={(e) => setMotDePasse(e.target.value)}
              className={champ}
            />
          </div>
          {erreur && (
            <p role="alert" className="m-0 text-[13.5px] font-semibold text-marque">
              {erreur}
            </p>
          )}
          <Button type="submit" disabled={envoi} className="mt-1 h-11 rounded-full text-[15px] font-bold">
            {inscription ? T.creerCompte : T.seConnecter}
          </Button>
        </form>

        <p className="mt-5 mb-0 text-center text-[13.5px] text-muted-ink">
          {inscription ? T.dejaUnCompte : T.pasDeCompte}{" "}
          <button
            type="button"
            className="font-bold text-ink hover:underline"
            onClick={() => {
              setMode(inscription ? "connexion" : "inscription");
              setErreur(null);
            }}
          >
            {inscription ? T.seConnecter : T.inscriptionTitre}
          </button>
        </p>
      </div>
    </main>
  );
}
