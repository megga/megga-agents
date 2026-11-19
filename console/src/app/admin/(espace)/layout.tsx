import { RailAdmin } from "@/components/admin/rail";
import { entreesRail } from "@/lib/admin/acces";
import { gardePage } from "@/lib/admin/garde";
import { imageDe } from "@/lib/admin/photo";
import { pret } from "@/lib/base";
import { serveurAgents } from "@/lib/serveur-agents";

// La coquille de l'admin : le rail à gauche, la page à droite. Elle vérifie le membre pour dessiner le rail ;
// chaque page le revérifie elle-même avec son droit (une mise en page ne se rejoue pas à la navigation).
export default async function CoquilleAdmin({ children }: LayoutProps<"/admin">) {
  const a = await gardePage();
  return (
    <div className="flex h-dvh">
      <RailAdmin entrees={entreesRail(a)} nom={a.nom || a.courriel} image={await imageDe(await pret(), a.utilisateur)} consoleAgents={serveurAgents() !== null} />
      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-5 px-8 pt-7 pb-14 max-[760px]:px-4 max-[760px]:pt-5">{children}</div>
      </main>
    </div>
  );
}

// Propre à chaque membre : rendue à la demande, après la vérification de la session.
export const instant = false;
