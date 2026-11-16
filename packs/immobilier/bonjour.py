"""Le mot du matin (demande d'un courtier, 16.11.2026 : « tous les matins, un message d'encouragement, avec de la bonne humeur, de la
joie ») : chaque jour à l'heure réglée (Config.bonjour, heure du client), l'agent écrit à chaque gestionnaire quelques
mots chaleureux pour bien commencer la journée. Claude les écrit, différents chaque jour ; sans lui, une phrase d'une
courte liste. Chacun peut l'arrêter, le reprendre ou changer l'heure (outil mot_du_matin).

Hors des 24 heures de WhatsApp, il ne part que par un modèle Meta « bonjour » s'il est réglé ; sinon il n'est pas
gardé pour plus tard : un « bonjour » de la veille n'a plus de sens.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
from zoneinfo import ZoneInfo

from agno.run import RunContext

from .annonces import Services

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre")
GARDES = 10  # les derniers mots gardés, pour ne pas se répéter

CONSIGNE = """Tu es l'assistante d'un courtier en immobilier de prestige ({entreprise}). Chaque matin, tu lui
envoies un petit mot sur WhatsApp pour bien commencer sa journée.
- Un message d'encouragement, plein de bonne humeur et de joie, sincère, jamais mièvre.
- Deux ou trois phrases courtes, en français, en le tutoyant. Tu peux saluer le jour ({jour}) ou la saison, glisser
  une touche d'humour léger ou une pensée positive sur son métier (les visites, les clients, les belles maisons).
- Au plus un émoji. Pas de liste, pas de titre, pas de guillemets, ni tiret long ni point médian.
- Rien d'inventé sur son agenda ou ses affaires, pas de conseil, pas de question.
- Chaque matin différent : jamais la même idée que ces derniers mots :
{derniers}
Réponds seulement par le message."""

SECOURS = (
    "Bonjour ! Une nouvelle journée commence, pleine de belles rencontres et de jolies maisons à faire aimer. Je suis là pour t'aider, belle journée à toi ☀️",
    "Bonjour ! Que cette journée t'apporte de bonnes nouvelles et de beaux sourires. On avance ensemble, je suis avec toi.",
    "Bonjour ! Un café, un grand sourire, et c'est parti pour une très belle journée. Tu fais un métier formidable, profite de chaque instant.",
    "Bonjour ! Le monde a besoin de gens passionnés comme toi. Je te souhaite une journée lumineuse et pleine d'élan 🌿",
    "Bonjour ! Aujourd'hui est une page blanche, et je suis sûre que tu vas y écrire de belles choses. Excellente journée !",
)


def prochain(maintenant: float, heure: str, fuseau: str) -> float:
    """La prochaine heure du mot du matin, strictement après `maintenant`."""
    z = ZoneInfo(fuseau)
    h, m = (int(x) for x in heure.split(":"))
    ici = dt.datetime.fromtimestamp(maintenant, z)
    t = ici.replace(hour=h, minute=m, second=0, microsecond=0)
    if t.timestamp() <= maintenant:
        t = (ici + dt.timedelta(days=1)).replace(hour=h, minute=m, second=0, microsecond=0)
    return t.timestamp()


def propre(texte: str) -> str | None:
    """Le mot écrit par Claude, s'il tient : une à quatre phrases, sans artefact ; sinon None."""
    t = re.sub(r"\s*[\u2014\u2013]\s*", ", ", str(texte or "")).replace("\u00b7", " ")
    t = " ".join(t.split()).strip(" \"«»")
    if not 30 <= len(t) <= 400 or re.search(r"[#*|<>{}\[\]]", t):
        return None
    return t


class Bonjour:
    def __init__(self, s: Services):
        self.s = s

    def reglage(self, numero: str) -> dict:
        r = self.s.etats.lire(numero, "bonjour") or {}
        return {"actif": r.get("actif", True), "heure": r.get("heure") or self.s.bonjour}

    async def echeance(self, maintenant: float) -> float | None:
        s = self.s
        if not s.bonjour:
            return None
        prochaines = []
        for numero in list((getattr(s.personnes, "gestionnaires", {}) or {})):
            if not s.personnes.compte(numero):
                continue
            r = await asyncio.to_thread(self.reglage, numero)
            if not r["actif"]:
                continue
            prevu = await asyncio.to_thread(s.etats.lire, numero, "bonjour_prochain")
            if prevu is None or prevu > maintenant + 2 * 86400:
                prevu = prochain(maintenant, r["heure"], s.fuseau)
                await asyncio.to_thread(s.etats.ecrire, numero, "bonjour_prochain", prevu)
            if prevu <= maintenant:
                suivant = prochain(maintenant, r["heure"], s.fuseau)
                await asyncio.to_thread(s.etats.ecrire, numero, "bonjour_prochain", suivant)
                if maintenant - prevu < 3 * 3600:  # réveillé trop tard (conteneur endormi) : pas de bonjour à midi
                    try:
                        await self.envoyer(numero, maintenant)
                    except Exception as e:
                        logging.getLogger("megga").error("mot du matin en échec : %s", str(e)[:200])
                prevu = suivant
            prochaines.append(prevu)
        return min(prochaines) if prochaines else None

    async def ecrire(self, numero: str, maintenant: float) -> str:
        s = self.s
        derniers = await asyncio.to_thread(s.etats.lire, numero, "bonjour_derniers") or []
        ici = dt.datetime.fromtimestamp(maintenant, ZoneInfo(s.fuseau))
        jour = f"{JOURS[ici.weekday()]} {ici.day} {MOIS[ici.month - 1]}"
        texte = None
        if s.assistante is not None and hasattr(s.assistante, "_texte"):
            try:
                texte = propre(await s.assistante._texte(
                    CONSIGNE.format(entreprise=s.marque or "l'agence", jour=jour,
                                    derniers="\n".join(f"- {d}" for d in derniers[-GARDES:]) or "- (aucun)"),
                    f"Écris le mot de ce {jour}.", 300))
            except Exception as e:
                logging.getLogger("megga").warning("mot du matin sans Claude : %s", str(e)[:200])
        if texte is None:
            texte = SECOURS[ici.toordinal() % len(SECOURS)]
        await asyncio.to_thread(s.etats.ecrire, numero, "bonjour_derniers", [*derniers, texte][-GARDES:])
        return texte

    async def envoyer(self, numero: str, maintenant: float) -> str:
        texte = await self.ecrire(numero, maintenant)
        s = self.s
        if s.conversations is not None:
            async with s.conversations.entre_les_tours(numero):
                await s.conversations.envoyer_de_soi_meme(numero, [{"texte": texte}], "bonjour", ["un petit mot pour bien commencer la journée"],
                                                          garder=False)
        else:
            await s.exp.texte(numero, texte)
        return texte

    def outils(self) -> list:
        s = self

        async def mot_du_matin(actif: bool, run_context: RunContext, heure: str = "") -> str:
            """Arrête, reprend ou déplace le mot d'encouragement du matin.

            Args:
                actif: faux pour l'arrêter, vrai pour le reprendre.
                heure: la nouvelle heure, « HH:MM » (heure locale), facultative.
            """
            numero = getattr(run_context, "user_id", "") or ""
            if not s.s.personnes.compte(numero):
                raise ValueError("le mot du matin est pour les gestionnaires")
            if not s.s.bonjour:
                return "Le mot du matin n'est pas en service pour cette agence."
            if heure and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", heure.strip()):
                raise ValueError("heure : HH:MM, par exemple 07:30")
            r = await asyncio.to_thread(s.reglage, numero)
            r = {"actif": bool(actif), "heure": heure.strip() or r["heure"]}
            await asyncio.to_thread(s.s.etats.ecrire, numero, "bonjour", r)
            await asyncio.to_thread(s.s.etats.ecrire, numero, "bonjour_prochain", None)
            return (f"Le mot du matin arrivera chaque jour à {r['heure'].replace(':', ' h ')}." if r["actif"]
                    else "Le mot du matin est arrêté. Il suffit de me le redemander pour le reprendre.")

        return [mot_du_matin]
