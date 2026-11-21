"""L'agent d'accueil des entreprises (lot E1, docs/clone-agent/11-espace-client.md).

On ne remplit plus d'écrans : le client raconte son entreprise, et cet agent écrit la configuration de son agent. Il ne
répond jamais aux clients de l'entreprise et n'agit dans aucun compte : il fait connaissance, note, propose un modèle,
prend le prénom, puis prépare un brouillon (une version de l'atelier), que le client essaie et met en service.

Ce qu'il note est gardé dans l'atelier (megga_reglages, une clé par client), sans conversation : les notes, le modèle
choisi, le prénom et le dernier brouillon. La conversation, elle, est celle d'Agno (sa base, une session par fil).

Ce qu'il écrit dans un brouillon : le modèle choisi (comme POST /clients/{id}/gabarit, mêmes règles), le prénom, le ton,
et la présentation de l'entreprise (Config.presentation). Jamais les consignes de MEGGA, le numéro, les modèles de
langue ni rien d'autre : un client qui lui demanderait autre chose n'obtient rien de plus que ce qu'il règle lui-même.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import unicodedata
from typing import Callable

from noyau.typographie import sans_artefacts

from . import gabarits, regles
from .regles import Refus

# Ce que l'agent note, et comment la présentation le range (en anglais : elle part dans les consignes de l'agent).
SUJETS = {
    "activite": "Business",
    "horaires": "Opening hours",
    "services": "Services and prices",
    "demandes": "What customers ask most",
    "regle": "Rules",
}
TON = "ton"  # noté à part : il va dans Config.ton, pas dans la présentation
NOTE_MAX = 600
TON_MAX = 200
PRESENTATION_MAX = 2000
RESULTATS = 5  # modèles rendus par une recherche
PRENOM = re.compile(r"^[^\W\d_][\w' .-]{0,39}$", re.UNICODE)

CONSIGNES = [
    "You are the MEGGA onboarding assistant. A business owner is creating the AI agent that will answer their own"
    " customers on WhatsApp and by voice. Your only job is to get to know their business and set that agent up.",
    "Always reply in the language the person writes in. Keep every message short, warm and plain. Ask one question at a"
    " time, never more. Never use a long dash or a middle dot.",
    "Start by asking them to describe their business. Then, as the conversation goes, find out: what customers ask most,"
    " opening hours, services (and public prices if they give them), any rule the agent must follow, and the tone they"
    " want. Call `noter` every time you learn one of these, with the person's own facts only. Never invent a fact.",
    "When you understand the business, call `chercher_modele` with a few words about it, propose the best match in one"
    " sentence, and call `choisir_modele` only after the person agrees. Then ask for the agent's first name and call"
    " `nommer_agent`.",
    "When you have the business, at least one more topic, a model and a first name, call `preparer_agent`. Then tell"
    " the person their agent is ready to try, and invite them to write to it as one of their customers would.",
    "You never answer as the business's agent, never promise what the agent will do beyond what was noted, and never"
    " ask for or keep a password, a card number or a code. If asked for something else (another account, other"
    " settings, MEGGA's own settings), say that the MEGGA team handles it.",
]


def cle(ident: str) -> str:
    """La clé de l'état dans megga_reglages (40 caractères au plus) : jamais l'identifiant seul, qui peut être plus long."""
    return "accueil:" + hashlib.sha256(ident.encode()).hexdigest()[:32]


def vide() -> dict:
    return {"notes": {}, "modele": None, "prenom": None, "version": None}


def presentation(notes: dict) -> str:
    """La présentation de l'entreprise, rangée par sujet, telle qu'elle part dans la configuration."""
    lignes = [f"{titre}: {notes[s]}" for s, titre in SUJETS.items() if notes.get(s)]
    return "\n".join(lignes)[:PRESENTATION_MAX]


def propre(texte: object, maximum: int) -> str:
    """Un texte d'une ligne ou plusieurs, sans tiret long ni point médian, borné."""
    if not isinstance(texte, str):
        raise Refus(400, "un texte est attendu")
    t = sans_artefacts(" ".join(texte.split()) if "\n" not in texte else "\n".join(" ".join(l.split()) for l in texte.splitlines()))
    t = t.strip()
    if not t:
        raise Refus(400, "un texte vide")
    return t[:maximum]


def _mots(texte: str) -> set[str]:
    sans_accents = unicodedata.normalize("NFKD", texte.lower()).encode("ascii", "ignore").decode()
    # Les six premières lettres : « immobilière » retrouve « immobilier », « agencies » retrouve « agency ».
    return {m[:6] for m in re.findall(r"[a-z0-9]{3,}", sans_accents)}


def chercher(recherche: str, zone: str | None) -> list[dict]:
    """Les modèles les plus proches de ces mots (titre, description, catégorie) ; le généraliste si rien ne colle."""
    voulus = _mots(recherche)
    notes = []
    for ident, g in gabarits.MODELES.items():
        if zone == "etats-unis" and ident in gabarits.PAS_AUX_ETATS_UNIS:
            continue
        titre = _mots(g["titre"] + " " + ident.replace("-", " "))
        corps = _mots(g["description"] + " " + (g.get("categorie") or ""))
        n = 3 * len(voulus & titre) + len(voulus & corps)
        if n and ident in gabarits.GABARITS:
            n += 2  # les modèles d'accueil, faits pour répondre aux clients d'une entreprise, passent devant
        if n:
            notes.append((-n, ident))
    choisis = [i for _, i in sorted(notes)[:RESULTATS - 1]]
    if "generaliste" not in choisis:  # toujours proposé : il accueille les clients de n'importe quelle entreprise
        choisis.append("generaliste")
    return [{"id": i, "titre": gabarits.MODELES[i]["titre"], "description": gabarits.MODELES[i]["description"][:240]}
            for i in choisis]


def outils(lire: Callable[[], dict], ecrire: Callable[[dict], None], zone: str | None,
           preparer: Callable[[dict], dict], verrou: threading.Lock) -> list[Callable]:
    """Les outils de l'agent d'accueil, sur l'état d'un client (`lire`, `ecrire`). `preparer` écrit le brouillon.
    `verrou` : celui du client, le même pour tous ses tours (deux onglets, MEGGA et le client en même temps)."""

    def repondre(d: dict) -> str:
        return json.dumps(d, ensure_ascii=False)


    def changer(f: Callable[[dict], object]) -> dict:
        with verrou:
            etat = lire()
            f(etat)
            ecrire(etat)
            return etat

    def noter(sujet: str, texte: str) -> str:
        """Save what the person said about their business. `sujet` is one of: activite (what the business does),
        horaires (opening hours), services (services and public prices), demandes (what customers ask most), regle
        (a rule the agent must follow), ton (the tone they want). `texte` replaces what was noted on that topic, so
        include everything still true. Returns all notes."""
        if sujet not in SUJETS and sujet != TON:
            return repondre({"erreur": "sujet : " + ", ".join([*SUJETS, TON])})
        try:
            t = propre(texte, TON_MAX if sujet == TON else NOTE_MAX)
        except Refus as e:
            return repondre({"erreur": e.message})
        etat = changer(lambda e: e["notes"].__setitem__(sujet, t))
        return repondre({"notes": etat["notes"]})

    def chercher_modele(recherche: str) -> str:
        """Find the agent models closest to the business, from a few words about it: give them both in the person's
        language and in English. Returns up to five models with their id, title and description."""
        return repondre({"modeles": chercher(recherche if isinstance(recherche, str) else "", zone)})

    def choisir_modele(modele: str) -> str:
        """Choose the agent model, by its id from `chercher_modele`, once the person has agreed to it."""
        if modele not in gabarits.MODELES or (zone == "etats-unis" and modele in gabarits.PAS_AUX_ETATS_UNIS):
            return repondre({"erreur": "modèle inconnu : prendre un id rendu par chercher_modele"})
        changer(lambda e: e.__setitem__("modele", modele))
        return repondre({"modele": modele, "titre": gabarits.MODELES[modele]["titre"]})

    def nommer_agent(prenom: str) -> str:
        """Set the first name of the business's agent (up to 40 characters)."""
        p = " ".join(prenom.split()) if isinstance(prenom, str) else ""
        if not PRENOM.fullmatch(p) or re.search(r"[\u2014\u2013\u00b7]", p):
            return repondre({"erreur": "un prénom de 1 à 40 lettres"})
        changer(lambda e: e.__setitem__("prenom", p))
        return repondre({"prenom": p})

    def preparer_agent() -> str:
        """Write the agent from everything noted: the chosen model, the first name, the tone and the business
        presentation. Call it once the person has described their business and chosen a model and a first name.
        Returns the draft version to try."""
        with verrou:
            etat = lire()
            manque = [m for m, ok in (("activite", etat["notes"].get("activite")), ("modele", etat["modele"]),
                                      ("prenom", etat["prenom"])) if not ok]
            if manque:
                return repondre({"erreur": "il manque encore : " + ", ".join(manque)})
            try:
                v = preparer(etat)
            except Refus as e:
                return repondre({"erreur": e.message})
            etat["version"] = v["version"]
            ecrire(etat)
        return repondre(v)

    return [noter, chercher_modele, choisir_modele, nommer_agent, preparer_agent]


def changements(etat: dict, base: dict, role: str) -> dict:
    """Ce que le brouillon change dans la base : le modèle (règles de POST /gabarit), le prénom, le ton, la présentation."""
    ch = gabarits.reglages_pour(etat["modele"], base)
    if role == "client" and not regles.consignes_de_gabarit(base.get("consignes", "")):
        ch.pop("consignes", None)  # celles que MEGGA a écrites sur mesure restent (comme POST /gabarit)
    ch["nom_agent"] = etat["prenom"]
    if etat["notes"].get(TON):
        ch["ton"] = etat["notes"][TON]
    ch["presentation"] = presentation(etat["notes"])
    return ch
