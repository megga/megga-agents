import { atelier, RefusChamps } from "@/lib/admin/atelier";
import { garde } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";

// Proposer une image à l'installation ({ version, image }) : un ordre signé part à son prochain relevé. Les formes sont celles
// que l'atelier exige (noyau/pilotage.py, VERSION_IMAGE et IMAGE), vérifiées ici d'abord pour dire, champ par champ, ce qui ne va
// pas ; la réponse de l'atelier, 201.
const VERSION_IMAGE = /^[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}$/;
const IMAGE = /^ghcr\.io\/megga\/megga-agents@sha256:[0-9a-f]{64}$/;

const lu = (corps: unknown) => {
  const c = (corps && typeof corps === "object" ? corps : {}) as { version?: unknown; image?: unknown };
  return { version: c.version, image: c.image };
};
const texte = (v: unknown) => (typeof v === "string" ? v : null);

export const POST = garde(
  {
    droit: "installations.gerer",
    client: (p: { id: string }) => p.id,
    action: "installation.image",
    detail: (corps) => ({ version: texte(lu(corps).version), image: texte(lu(corps).image) }),
  },
  async ({ params, corps }) => {
    const { version, image } = lu(corps);
    const champs = [
      ...(typeof version === "string" && VERSION_IMAGE.test(version) ? [] : [{ champ: "version", message: TA.versionImageAttendue }]),
      ...(typeof image === "string" && IMAGE.test(image) ? [] : [{ champ: "image", message: TA.imageAttendue }]),
    ];
    if (champs.length) throw new RefusChamps(400, TA.imageInvalide, champs);
    return Response.json(await atelier.proposerImage(params.id, { version, image }), { status: 201 });
  },
);
