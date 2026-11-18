"use client";

import { useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import { CLE_JETON, Rejoindre } from "./[jeton]/rejoindre";

const sansAbonnement = () => () => {};

function jetonRange(): string | null {
  try {
    return sessionStorage.getItem(CLE_JETON);
  } catch {
    return null; // sans stockage, pas de jeton
  }
}

/**
 * Au retour de la connexion : le jeton rangé par la page d'invitation est relu, effacé, et la page du lien rouverte.
 * Sans jeton rangé, l'invitation se montre invalide. Rien avant que le navigateur ait lu (undefined côté serveur).
 */
export function Reprise() {
  const router = useRouter();
  const jeton = useSyncExternalStore(sansAbonnement, jetonRange, () => undefined);

  useEffect(() => {
    if (!jeton) return;
    try {
      sessionStorage.removeItem(CLE_JETON);
    } catch {
      // déjà lu : rien à effacer
    }
    router.replace(`/admin/invitation/${encodeURIComponent(jeton)}`);
  }, [jeton, router]);

  return jeton === null ? <Rejoindre etat="invalide" jeton="" courriel="" /> : null;
}
