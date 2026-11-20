"""Le serveur d'agents de l'essai local de la console (lot 8.1).

Il tient la place de l'atelier tant que celui-ci ne sait ni servir plusieurs agents par compte,
ni répondre en AG-UI (docs/superpowers/specs/2026-11-17-console-socle-design.md). Il ne modifie
pas le moteur : il lit les consignes des gabarits (`atelier.gabarits`) et du noyau
(`noyau.agent.consignes`), et fait répondre un agent Agno par l'interface AG-UI d'Agno.

Lancement : `AGENTS_JETON=… .venv/bin/python -m uvicorn serveur:app --app-dir console/agents --host 127.0.0.1 --port 8100`
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from ag_ui.core import RunAgentInput
from ag_ui.encoder import EventEncoder
from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.base import Model
from agno.models.response import ModelResponse
from agno.session.summary import SessionSummaryManager
from agno.os.interfaces.agui.router import run_entity
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from atelier import gabarits
from atelier.regles import Refus
from noyau import stockage
from noyau.agent import consignes, modele
from noyau.config import Config
from noyau.echanges import Collegue, Relais, collegue_agno

journal = logging.getLogger("megga.console.agents")

# Les huit métiers du lot 10 (atelier/gabarits/ sur la branche megga/lot-10-modeles).
METIERS = ("generaliste", "immobilier", "sante", "hotellerie", "juridique", "commerce", "fiduciaire", "garage")
# L'agent de l'essai n'a aucun outil (ni rappels, ni catalogue, ni transfert) : qu'il ne promette rien de ce qu'il ne fait pas.
ESSAI = (
    "Dans cet essai, tu n'as aucun outil : ne promets ni rappel, ni réservation, ni rendez-vous ferme. "
    "Recueille la demande et propose de la transmettre à l'équipe."
)
# Avec des collègues, son seul outil : leur poser une question (noyau/echanges.py).
ESSAI_COLLEGUES = (
    "Dans cet essai, ton seul outil sert à poser une question à un collègue : ne promets ni rappel, ni réservation, "
    "ni rendez-vous ferme. Recueille la demande et propose de la transmettre à l'équipe."
)
# Ce que chaque agent sait du métier d'un collègue (les noms du Studio, console/src/lib/metiers.ts).
QUI = {
    "generaliste": "à l'accueil de l'entreprise",
    "immobilier": "à l'accueil de l'agence immobilière",
    "sante": "à l'accueil du cabinet",
    "hotellerie": "à l'accueil de l'établissement",
    "juridique": "au premier contact de l'étude",
    "commerce": "au service après-vente de la boutique",
    "fiduciaire": "à l'accueil de la fiduciaire",
    "garage": "à l'accueil du garage",
}
# Le résumé d'une conversation, en une phrase : la ligne de la page Activité (maquette « Temps forts »).
RESUME = (
    "Prénom de l'agent : {prenom}.\n"
    "Résume en une seule phrase courte, au passé composé et à la troisième personne, ce que {prenom} a fait dans cette "
    "conversation, en commençant par « {prenom} ». Exemples : « {prenom} a confirmé la visite de jeudi à 14 h », "
    "« {prenom} a transmis la demande de devis à l'équipe ». Écris en français, sans tiret long ni point médian. "
    "N'invente rien : seulement ce que la conversation montre. Pas de numéro de téléphone, de courriel ni de donnée "
    "de santé ou bancaire.\n"
)
IDENT = re.compile(r"^[A-Za-z0-9_-]{6,64}$")

DOSSIER = Path(os.environ.get("AGENTS_DONNEES") or Path(__file__).resolve().parent.parent / ".donnees")
DOSSIER.mkdir(parents=True, exist_ok=True)
REGISTRE = DOSSIER / "agents.json"


@dataclass
class ModeleEssai(Model):
    """Un modèle qui répond sans réseau quand aucune clé n'est posée (essais et CI)."""

    id: str = "essai"
    name: str = "Essai"
    provider: str = "essai"
    vus: list = field(default_factory=list)

    def _repondre(self, messages):
        des_gens = [m for m in (messages or []) if getattr(m, "role", "") == "user"]
        texte = str(getattr(des_gens[-1], "content", "") or "") if des_gens else ""
        if texte == "ESSAI-PANNE":  # les essais de bout en bout simulent ainsi une panne du modèle
            raise RuntimeError("panne simulée du modèle d'essai")
        # Le résumé d'une conversation (RESUME) : la première demande, telle quelle.
        systeme = str(getattr(messages[0], "content", "") or "") if messages else ""
        if "<conversation>" in systeme:
            prenom = re.search(r"Prénom de l'agent : (.+?)\.", systeme)
            demande = re.search(r"User: (.+)", systeme)
            debut = (demande.group(1).removeprefix("ESSAI-COLLEGUE ") if demande else "")[:80]
            return ModelResponse(role="assistant", content=json.dumps(
                {"summary": f"{prenom.group(1) if prenom else 'L agent'} a répondu à «\u00a0{debut}\u00a0»"}))
        # « ESSAI-COLLEGUE <question> » : il pose la question à son premier collègue, puis redit sa réponse.
        if texte.startswith("ESSAI-COLLEGUE "):
            retour = next((m for m in reversed(messages) if getattr(m, "role", "") == "tool"), None)
            if retour is not None:
                return ModelResponse(role="assistant", content="Voici ce que mon collègue m'a répondu.")
            consignes = "\n".join(str(getattr(m, "content", "") or "") for m in messages if getattr(m, "role", "") == "system")
            collegue = re.search(r"^- .+? \(([A-Za-z0-9_-]+)\) :", consignes, re.M)
            if collegue:
                arguments = json.dumps({"collegue": collegue.group(1), "question": texte.removeprefix("ESSAI-COLLEGUE ")})
                return ModelResponse(role="assistant", tool_calls=[{"id": f"essai-{len(messages)}", "type": "function",
                                                                    "function": {"name": "demander_a_un_collegue", "arguments": arguments}}])
        reponse = f"Bien reçu\u00a0: «\u00a0{texte}\u00a0». Je transmets à l'équipe."
        # Il compte les messages de la conversation qu'il voit : les essais vérifient ainsi qu'il s'en souvient.
        if len(des_gens) > 1:
            reponse += f" C'est votre {len(des_gens)}e message."
        return ModelResponse(role="assistant", content=reponse)

    def invoke(self, messages=None, **kw):
        return self._repondre(messages)

    async def ainvoke(self, messages=None, **kw):
        return self._repondre(messages)

    def invoke_stream(self, messages=None, **kw):
        yield self._repondre(messages)

    async def ainvoke_stream(self, messages=None, **kw):
        yield self._repondre(messages)

    def _parse_provider_response(self, response, **kw):
        return response

    def _parse_provider_response_delta(self, response):
        return response


class Inscription(BaseModel):
    prenom: str = Field(min_length=1, max_length=20)
    metier: str
    entreprise: str = Field(min_length=1, max_length=120)
    # Le compte du client : les agents d'un même compte sont collègues et peuvent se poser des questions.
    compte: str | None = Field(default=None, min_length=1, max_length=100)


# Les inscriptions arrivent en parallèle (FastAPI les sert dans plusieurs fils) : une à la fois.
VERROU = threading.Lock()


def lire_registre() -> dict:
    try:
        return json.loads(REGISTRE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def ecrire_registre(r: dict) -> None:
    """Écrit à côté, puis remplace : le registre n'est jamais lu à moitié écrit."""
    provisoire = REGISTRE.with_suffix(".json.tmp")
    provisoire.write_text(json.dumps(r, ensure_ascii=False, indent=1))
    os.replace(provisoire, REGISTRE)


def reglages(metier: str) -> dict:
    """Les réglages du gabarit ; un métier que cette image ne connaît pas encore prend ceux du généraliste."""
    try:
        return gabarits.reglages_pour(metier, {})
    except Refus:
        journal.warning("le métier %s n'est pas dans cette image (lot 10 non fusionné) : consignes du généraliste", metier)
        return gabarits.reglages_pour("generaliste", {})


def collegues_de(ident: str, fiche: dict, registre: dict) -> dict[str, dict]:
    """Les autres agents du même compte ; aucun pour un agent inscrit sans compte."""
    compte = fiche.get("compte")
    if not compte:
        return {}
    return {i: f for i, f in registre.items() if i != ident and f.get("compte") == compte}


def relais_de(ident: str, fiche: dict, registre: dict) -> Relais | None:
    """Le relais qui porte les questions de cet agent à ses collègues, chacun construit seulement s'il est interrogé."""
    autres = collegues_de(ident, fiche, registre)
    if not autres:
        return None
    relais = Relais(stockage.Echanges(f"sqlite:///{DOSSIER / 'echanges.sqlite'}"), noms={ident: fiche["prenom"]})
    for i, f in autres.items():

        async def repondre(question, de, origine, conclure=False, i=i, f=f):
            return await collegue_agno(construire(i, f, registre), f["prenom"], QUI[f["metier"]]).repondre(question, de, origine, conclure)

        relais.inscrire(i, Collegue(f["prenom"], QUI[f["metier"]], repondre))
    return relais


def construire(ident: str, fiche: dict, registre: dict | None = None) -> Agent:
    r = reglages(fiche["metier"])
    relais = relais_de(ident, fiche, lire_registre() if registre is None else registre)
    config = Config.model_validate({
        "id": "essai-" + re.sub(r"[^a-z0-9-]", "", ident.lower())[:40],
        "nom_agent": fiche["prenom"],
        "entreprise": fiche["entreprise"],
        "zone": "europe",
        "metier": r["metier"] if r["metier"] in ("general", "immobilier") else "general",
        "ton": r.get("ton", "chaleureux et professionnel"),
        "consignes": r.get("consignes", ""),
    })
    cle = os.environ.get("ANTHROPIC_API_KEY")
    m = modele(config.modeles.principal, {"ANTHROPIC_API_KEY": cle}) if cle else ModeleEssai()

    return Agent(
        id=ident,
        name=fiche["prenom"],
        model=m,
        instructions=[*consignes(config), ESSAI_COLLEGUES if relais else ESSAI, *([relais.consigne(ident)] if relais else [])],
        tools=relais.outils(ident) if relais else [],
        db=SqliteDb(db_file=str(DOSSIER / "sessions.sqlite")),
        add_history_to_context=True,
        num_history_runs=12,
        markdown=False,
        telemetry=False,
    )


def resumeur(fiche: dict) -> SessionSummaryManager:
    """Le résumé d'une conversation, par le petit modèle : un appel court de plus par tour, fait après la réponse."""
    cle = os.environ.get("ANTHROPIC_API_KEY")
    config = Config.model_validate({"id": "essai-resume", "nom_agent": fiche["prenom"], "entreprise": fiche["entreprise"], "zone": "europe"})
    petit = modele(config.modeles.petit(), {"ANTHROPIC_API_KEY": cle}, jetons=300) if cle else ModeleEssai()
    return SessionSummaryManager(model=petit, session_summary_prompt=RESUME.format(prenom=fiche["prenom"]), last_n_runs=6)


# Les résumés en cours, gardés jusqu'à leur fin (une tâche sans référence peut être oubliée en route).
RESUMES: set = set()


async def resumer(agent: Agent, fiche: dict, session_id: str) -> None:
    """Résume la conversation une fois la réponse partie : l'écran n'attend pas le résumé pour envoyer le message suivant.
    Un échec ne touche ni la conversation ni la réponse ; il est seulement noté."""
    try:
        session = agent.get_session(session_id=session_id)
        if session is not None and await resumeur(fiche).acreate_session_summary(session) is not None:
            agent.save_session(session)
    except Exception as e:
        journal.warning("résumé de conversation impossible : %s", str(e)[:200])


def jeton(requete: Request) -> None:
    attendu = os.environ.get("AGENTS_JETON", "")
    recu = (requete.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    if not attendu or not hmac.compare_digest(recu, attendu):
        raise HTTPException(401, "jeton refusé")


app = FastAPI(title="Agents de l'essai local de la console MEGGA", docs_url=None, redoc_url=None, openapi_url=None)
encodeur = EventEncoder()


@app.get("/sante")
def sante():
    return {"ok": True}


@app.put("/agents/{ident}", dependencies=[Depends(jeton)])
def inscrire(ident: str, corps: Inscription):
    if not IDENT.match(ident):
        raise HTTPException(400, "identifiant invalide")
    if corps.metier not in METIERS:
        raise HTTPException(400, "métier inconnu")
    with VERROU:
        r = lire_registre()
        r[ident] = corps.model_dump()
        ecrire_registre(r)
    return {"id": ident, "en_service": True}


@app.get("/comptes/{compte}/echanges", dependencies=[Depends(jeton)])
def echanges(compte: str, depuis: float = 0, limite: int = 200):
    """Les questions que les agents de ce compte se sont posées depuis cette date, la plus récente d'abord (page Activité).
    Ni les questions refusées par les garde-fous, ni celles d'un autre compte."""
    if not 1 <= len(compte) <= 100:
        raise HTTPException(400, "compte invalide")
    registre = lire_registre()
    agents = {i for i, f in registre.items() if f.get("compte") == compte}
    lignes = stockage.Echanges(f"sqlite:///{DOSSIER / 'echanges.sqlite'}").recents(depuis, agents, max(1, min(limite, 500)))
    return {"echanges": [{"id": l["id"], "quand": l["quand"], "de": l["de"], "a": l["a"], "question": l["texte"], "etat": l["etat"],
                          "reponse": l["reponse"]}
                         for l in lignes if l["etat"] != "refuse" and l["de"] in agents and l["a"] in agents]}


def tours(depuis: float, agents: set[str]) -> tuple[int, int]:
    """Les conversations et les réponses des agents depuis cette date, d'après les tours d'Agno ; sans les questions
    qu'ils se posent entre eux (leur conversation commence par « collegue: »)."""
    import sqlite3

    if not agents:
        return 0, 0
    fichier = DOSSIER / "sessions.sqlite"
    if not fichier.exists():
        return 0, 0
    marques = ",".join("?" * len(agents))
    with sqlite3.connect(f"file:{fichier}?mode=ro", uri=True) as c:
        try:
            n_conv, n_rep = c.execute(
                f"SELECT COUNT(DISTINCT session_id), SUM(status = 'COMPLETED') FROM agno_runs WHERE created_at >= ? "
                f"AND agent_id IN ({marques}) AND (user_id IS NULL OR user_id NOT LIKE 'collegue:%')",
                (int(depuis), *sorted(agents))).fetchone()
        except sqlite3.OperationalError:  # aucune conversation encore : Agno n'a pas créé sa table
            return 0, 0
    return int(n_conv or 0), int(n_rep or 0)


def _json(v):
    if isinstance(v, (dict, list)) or v is None:
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return None


@app.get("/comptes/{compte}/conversations", dependencies=[Depends(jeton)])
def conversations(compte: str, depuis: float = 0, limite: int = 100):
    """Les conversations des agents de ce compte actives depuis cette date, la plus récente d'abord : le résumé d'Agno en
    une phrase, et les étapes (aujourd'hui, les questions posées à un collègue, avec l'échange qui leur correspond).
    Sans les conversations entre agents eux-mêmes."""
    import sqlite3

    if not 1 <= len(compte) <= 100:
        raise HTTPException(400, "compte invalide")
    registre = lire_registre()
    agents = sorted(i for i, f in registre.items() if f.get("compte") == compte)
    fichier = DOSSIER / "sessions.sqlite"
    if not agents or not fichier.exists():
        return {"conversations": []}
    marques = ",".join("?" * len(agents))
    with sqlite3.connect(f"file:{fichier}?mode=ro", uri=True) as c:
        try:
            sessions = c.execute(
                f"SELECT session_id, agent_id, summary, updated_at FROM agno_sessions WHERE updated_at >= ? AND agent_id IN ({marques}) "
                f"AND (user_id IS NULL OR user_id NOT LIKE 'collegue:%') ORDER BY updated_at DESC, rowid DESC LIMIT ?",
                (int(depuis), *agents, max(1, min(limite, 500)))).fetchall()
            ids = [s[0] for s in sessions]
            runs = c.execute(f"SELECT session_id, run_data FROM agno_runs WHERE session_id IN ({','.join('?' * len(ids))}) "
                             "ORDER BY created_at", ids).fetchall() if ids else []
        except sqlite3.OperationalError:
            return {"conversations": []}
    depot = stockage.Echanges(f"sqlite:///{DOSSIER / 'echanges.sqlite'}")
    recents = depot.recents(depuis, set(agents), 500)
    etapes: dict[str, list] = {}
    for sid, brut in runs:
        for t in (_json(brut) or {}).get("tools") or []:
            if t.get("tool_name") != "demander_a_un_collegue":
                continue
            args = t.get("tool_args") or {}
            echange = next((e for e in recents if e["a"] == args.get("collegue") and e["texte"] == args.get("question")), None)
            etapes.setdefault(sid, []).append({"collegue": args.get("collegue", ""), "question": args.get("question", ""),
                                               "echange": echange["id"] if echange else None,
                                               "reponse": echange["reponse"] if echange else None,
                                               "etat": echange["etat"] if echange else None})
    return {"conversations": [{"id": sid, "agent": agent, "quand": quand, "resume": (_json(resume) or {}).get("summary"),
                               "etapes": etapes.get(sid, [])}
                              for sid, agent, resume, quand in sessions]}


@app.get("/comptes/{compte}/mesures", dependencies=[Depends(jeton)])
def mesures(compte: str, depuis: float = 0):
    """Les trois chiffres de la page Activité pour ce compte depuis cette date : tous tirés de ce qui s'est passé."""
    if not 1 <= len(compte) <= 100:
        raise HTTPException(400, "compte invalide")
    agents = {i for i, f in lire_registre().items() if f.get("compte") == compte}
    conversations, reponses = tours(depuis, agents)
    echanges = stockage.Echanges(f"sqlite:///{DOSSIER / 'echanges.sqlite'}").compter(depuis, agents)
    return {"conversations": conversations, "reponses": reponses, "echanges": echanges}


@app.post("/agents/{ident}/agui", dependencies=[Depends(jeton)])
async def repondre(ident: str, entree: RunAgentInput):
    fiche = lire_registre().get(ident)
    if fiche is None:
        raise HTTPException(404, "agent inconnu")
    agent = construire(ident, fiche)

    async def flux():
        async for evenement in run_entity(agent, entree, user_id=ident):
            yield encodeur.encode(evenement)
        # Le résumé part à côté, une fois le dernier événement envoyé : la réponse se termine sans l'attendre.
        tache = asyncio.create_task(resumer(agent, fiche, entree.thread_id))
        RESUMES.add(tache)
        tache.add_done_callback(RESUMES.discard)

    return StreamingResponse(flux(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
