"""Les recherches des clients, rapprochées deux fois par jour (demande d'un courtier, 16.11.2026).

Le courtier garde dans la gestion ce que cherchent ses clients (à la main, ou dicté à l'agent : recherche_client). Le matin et
le soir (8 h et 18 h, à l'heure de l'agence), l'agent relit ces recherches et les biens qui leur correspondent (la
gestion fait la correspondance) ; s'il y en a de nouveaux depuis le dernier passage, il prévient le courtier de la
recherche, en un message. Une recherche qu'il n'avait jamais vue ne prévient pas : à sa création, l'outil a déjà dit ce
qui correspondait. Rien n'est envoyé au client lui-même.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from zoneinfo import ZoneInfo

from .annonces import Services, court
from .gestion import GestionErreur

HEURES = (8, 18)
PAR_MESSAGE = 8  # biens cités au plus dans un message


def prochain_passage(maintenant: float, fuseau: str) -> float:
    """La prochaine heure de passage (8 h ou 18 h, à l'heure de l'agence) strictement après `maintenant`."""
    z = ZoneInfo(fuseau)
    ici = dt.datetime.fromtimestamp(maintenant, z)
    for jour in (0, 1):
        for h in HEURES:
            t = (ici + dt.timedelta(days=jour)).replace(hour=h, minute=0, second=0, microsecond=0)
            if t.timestamp() > maintenant:
                return t.timestamp()
    raise AssertionError("aucun passage")


def texte_nouveautes(nouveautes: list[tuple[str, list[dict]]]) -> str:
    """Le message au courtier : un bloc par client, une ligne par bien."""
    n = sum(len(b) for _, b in nouveautes)
    blocs = [f"*Recherches clients*\n{'Un nouveau bien correspond' if n == 1 else f'{n} nouveaux biens correspondent'} "
             "à ce que cherchent tes clients."]
    cites = 0
    for nom, biens in nouveautes:
        lignes = []
        for b in biens:
            if cites >= PAR_MESSAGE:
                break
            cites += 1
            lignes.append(f"- {court(b.get('titre'), 70)}, {b.get('localite', '')}{', ' + str(b['prix']) if b.get('prix') else ''}")
        if lignes:
            blocs.append(f"*{court(nom, 60) or 'Un client'}*\n" + "\n".join(lignes))
    if cites < n:
        blocs.append(f"Et {n - cites} de plus : demande-moi les biens d'une recherche pour tout voir.")
    blocs.append("Je prépare un message pour l'un d'eux ?")
    return "\n\n".join(blocs)


class SuiviRecherches:
    def __init__(self, s: Services):
        self.s = s

    async def echeance(self, maintenant: float) -> float | None:
        """Les gestionnaires dont l'heure de passage est venue ; rend la prochaine heure."""
        s = self.s
        prochaines = []
        for numero in list((getattr(s.personnes, "gestionnaires", {}) or {})):
            if not s.personnes.compte(numero):
                continue
            prevu = await asyncio.to_thread(s.etats.lire, numero, "recherches_passage")
            if prevu is None or prevu > maintenant + 2 * 86400:  # premier passage, ou fuseau changé
                prevu = prochain_passage(maintenant, s.fuseau)
                await asyncio.to_thread(s.etats.ecrire, numero, "recherches_passage", prevu)
            if prevu <= maintenant:
                prevu = prochain_passage(maintenant, s.fuseau)
                # Réservé avant le passage : un échec attend le suivant, il ne repasse pas en boucle.
                await asyncio.to_thread(s.etats.ecrire, numero, "recherches_passage", prevu)
                try:
                    await self.passer(numero)
                except Exception as e:
                    logging.getLogger("megga").error("recherches clients en échec : %s", str(e)[:200])
            prochaines.append(prevu)
        return min(prochaines) if prochaines else None

    async def passer(self, numero: str) -> str | None:
        """Un passage pour ce gestionnaire : le message envoyé, ou None s'il n'y a rien de nouveau."""
        s = self.s
        compte = s.personnes.compte(numero)
        try:
            clients = await s.gestion.appel(compte, "GET", "/clients")
            resume = await s.gestion.appel(compte, "GET", "/resume")
        except GestionErreur as e:
            raise ValueError(f"la gestion du site refuse : {e.message}") from e
        moi = (resume.get("moi") or {}).get("courtier")
        if not moi:
            return None  # un compte sans courtier ne suit les recherches de personne (relecture du 16.11.2026)
        annonces = {a.get("slug"): a for a in resume.get("annonces") or [] if not a.get("masquee")}
        vues = await asyncio.to_thread(s.etats.lire, numero, "recherches_vues") or {}
        apres, nouveautes = {}, []
        for r in clients.get("recherches") or []:
            if r.get("courtier") != moi:
                continue  # celles d'un autre courtier (un admin les voit toutes) : à lui de les suivre
            slugs = [x for x in r.get("biens") or [] if x in annonces]
            # Les biens vus s'ajoutent, ne se retirent jamais : une annonce masquée puis réaffichée, ou une réponse
            # incomplète de la gestion, ne repasse pas pour une nouveauté.
            deja = vues.get(r["id"])
            apres[r["id"]] = list(dict.fromkeys([*(deja or []), *slugs]))[-500:]
            if deja is None:
                continue
            neufs = [annonces[x] for x in slugs if x not in deja]
            if neufs:
                nouveautes.append(((r.get("client") or {}).get("nom", ""), neufs))
        if not nouveautes:
            await asyncio.to_thread(s.etats.ecrire, numero, "recherches_vues", apres)
            return None
        texte = texte_nouveautes(nouveautes)
        n = sum(len(b) for _, b in nouveautes)
        annonce = "un nouveau bien correspond à la recherche d'un client" if n == 1 else f"{n} nouveaux biens correspondent aux recherches de vos clients"
        if s.conversations is not None:
            async with s.conversations.entre_les_tours(numero):
                await s.conversations.envoyer_de_soi_meme(numero, [{"texte": texte}], "rapprochement", [annonce])
        else:
            await s.exp.texte(numero, texte)
        # Notés vus seulement une fois le message parti : un envoi en échec les signale au passage suivant.
        await asyncio.to_thread(s.etats.ecrire, numero, "recherches_vues", apres)
        return texte
