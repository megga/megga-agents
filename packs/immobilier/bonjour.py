"""Le mot du matin (demande d'un courtier, 16.11.2026 : « tous les matins, un message d'encouragement, avec de la bonne humeur, de la
joie ») : chaque jour à l'heure réglée (Config.bonjour, heure du client), l'agent écrit à chaque gestionnaire quelques
mots chaleureux pour bien commencer la journée. Claude les écrit, différents chaque jour ; sans lui, une phrase d'une
courte liste. Chacun peut l'arrêter, le reprendre ou changer l'heure (outil mot_du_matin).

Hors des 24 heures de WhatsApp (le courtier n'a pas écrit depuis la veille), il ne part que par un modèle Meta
« bonjour » s'il est réglé ; sinon ce matin-là est sauté, sans appel à Claude, et noté au journal du suivi : un
« bonjour » gardé pour plus tard n'aurait plus de sens. Un seul mot par jour, même si l'heure change.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
import time
from zoneinfo import ZoneInfo

from noyau.whatsapp import fenetre_ouverte

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
- Commence par « Bonjour ! » et ne finis pas par un souhait de « belle journée » ou de « bonne journée ».
- Rien d'inventé : ni sur son agenda ou ses affaires, ni sur la météo, une fête ou un événement. Pas de conseil, pas
  de question, pas de préambule (« Voici… »).
- Chaque matin différent : jamais la même idée que ces derniers mots :
{derniers}
Réponds seulement par le message."""

SECOURS = (
    "Bonjour ! Une nouvelle journée commence, pleine de belles rencontres et de jolies maisons à faire aimer ☀️",
    "Bonjour ! Que cette journée t'apporte de bonnes nouvelles et de beaux sourires, je suis avec toi.",
    "Bonjour ! Un café, un grand sourire, et c'est parti : tu fais un métier formidable, profite de chaque instant.",
    "Bonjour ! Le monde a besoin de gens passionnés comme toi, et ta journée sera lumineuse et pleine d'élan 🌿",
    "Bonjour ! Aujourd'hui est une page blanche, et je suis sûre que tu vas y écrire de belles choses.",
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


EMOJI = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]")


def variable_du_modele(texte: str) -> str:
    """Le mot tel que le modèle fsp_agent_bonjour le porte : sans sa salutation (le modèle dit déjà « Bonjour »), sans
    ponctuation ni émoji final (le modèle ajoute « . Belle journée à vous. »), sur une ligne."""
    v = " ".join(str(texte or "").split())
    v = re.sub(r"^(bonjour|salut|coucou|hello|hey)\b[\s,!.]*", "", v, flags=re.I)
    v = re.sub(r"[\s.!\u2026\ufe0f\U0001F000-\U0001FAFF\u2600-\u27BF]+$", "", v)
    return (v[:1].upper() + v[1:])[:900] if v else " ".join(str(texte or "").split())[:900]


def propre(texte: str) -> str | None:
    """Le mot écrit par Claude, s'il tient à la consigne : une à quatre phrases, au plus un émoji, sans question, sans
    préambule ni point médian ; sinon None (la phrase de secours part)."""
    brut = str(texte or "")
    if (len(EMOJI.findall(brut)) > 1 or "?" in brut or re.search(r"[\u00b7\u2022\u22c5]", brut)
            or re.match(r"\s*voici\b", brut, re.I) or ":" in brut[:40]):
        return None
    t = re.sub(r"\s*[\u2014\u2013]\s*", ", ", brut)
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
                # Déjà reçu aujourd'hui (l'heure vient de changer) : à partir de demain.
                if await asyncio.to_thread(s.etats.lire, numero, "bonjour_jour") == self.jour(maintenant) and \
                        self.jour(prevu) == self.jour(maintenant):
                    prevu = prochain(prevu, r["heure"], s.fuseau)
                await asyncio.to_thread(s.etats.ecrire, numero, "bonjour_prochain", prevu)
            if prevu <= maintenant:
                suivant = prochain(maintenant, r["heure"], s.fuseau)
                await asyncio.to_thread(s.etats.ecrire, numero, "bonjour_prochain", suivant)
                if maintenant - prevu < 3 * 3600:  # réveillé trop tard (conteneur endormi) : pas de bonjour à midi
                    try:
                        await self.envoyer(numero, maintenant)
                    except Exception as e:
                        logging.getLogger("megga").error("mot du matin en échec : %s", str(e)[:200])
                        self.journal("bonjour_echec", type(e).__name__)
                prevu = suivant
            prochaines.append(prevu)
        return min(prochaines) if prochaines else None

    def jour(self, t: float) -> str:
        return dt.datetime.fromtimestamp(t, ZoneInfo(self.s.fuseau)).date().isoformat()

    def journal(self, genre: str, detail: str = "") -> None:
        conv = self.s.conversations
        if conv is not None and hasattr(conv, "noter_journal"):
            conv.noter_journal(genre, detail=detail)

    async def joignable(self, numero: str) -> bool:
        """Le mot peut-il partir ? Dans les 24 heures du dernier message du courtier, ou par un modèle Meta « bonjour »."""
        conv = self.s.conversations
        if conv is None:
            return True
        if getattr(getattr(conv, "conf", None), "modeles_meta", {}).get("bonjour"):
            return True
        contacts = getattr(conv, "contacts", None)
        dernier = await asyncio.to_thread(contacts.dernier, numero) if contacts is not None else None
        return fenetre_ouverte(dernier, time.time())

    async def ecrire(self, numero: str, maintenant: float) -> str:
        s = self.s
        derniers = await asyncio.to_thread(s.etats.lire, numero, "bonjour_derniers") or []
        ici = dt.datetime.fromtimestamp(maintenant, ZoneInfo(s.fuseau))
        jour = f"{JOURS[ici.weekday()]} {ici.day} {MOIS[ici.month - 1]}"
        texte = None
        if s.assistante is not None and hasattr(s.assistante, "_texte"):
            try:
                texte = propre(await asyncio.wait_for(s.assistante._texte(
                    CONSIGNE.format(entreprise=s.marque or "l'agence", jour=jour,
                                    derniers="\n".join(f"- {d}" for d in derniers[-GARDES:]) or "- (aucun)"),
                    f"Écris le mot de ce {jour}.", 300), 25))
            except Exception as e:
                logging.getLogger("megga").warning("mot du matin sans Claude : %s", str(e)[:200])
        if texte is None:
            texte = SECOURS[ici.toordinal() % len(SECOURS)]
        await asyncio.to_thread(s.etats.ecrire, numero, "bonjour_derniers", [*derniers, texte][-GARDES:])
        return texte

    async def envoyer(self, numero: str, maintenant: float) -> str | None:
        """Le mot du jour, s'il peut partir ; sinon rien (ni Claude, ni mot rangé) et une ligne au journal."""
        s = self.s
        if not await self.joignable(numero):
            self.journal("bonjour_attente", "hors des 24 heures, sans modèle")
            return None
        texte = await self.ecrire(numero, maintenant)
        await asyncio.to_thread(s.etats.ecrire, numero, "bonjour_jour", self.jour(maintenant))
        if s.conversations is not None:
            async with s.conversations.entre_les_tours(numero):
                # Hors des 24 heures, le modèle fsp_agent_bonjour porte le mot lui-même : « … demandé : {{1}}. Belle
                # journée à vous. » (sans retour à la ligne ni point final, que le modèle ajoute).
                variable = variable_du_modele(texte)
                await s.conversations.envoyer_de_soi_meme(numero, [{"texte": texte}], "bonjour", [variable], garder=False)
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
            avec_modele = bool(getattr(getattr(s.s.conversations, "conf", None), "modeles_meta", {}).get("bonjour"))
            condition = "" if avec_modele or s.s.conversations is None else ", si tu m'as écrit depuis la veille"
            return (f"Le mot du matin arrivera chaque jour à {r['heure'].replace(':', ' h ')}{condition}." if r["actif"]
                    else "Le mot du matin est arrêté. Il suffit de me le redemander pour le reprendre.")

        return [mot_du_matin]
