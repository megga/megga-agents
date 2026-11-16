"""Le serveur d'un agent : une image, un client par conteneur.

Variables d'environnement (jamais dans le dépôt) :
  CLIENT_CONFIG        la configuration du client, en JSON (ou CLIENT_CONFIG_FILE, un chemin)
  DATABASE_URL         la base du client (noyau/stockage.py)
  META_TOKEN           le jeton de l'app Meta, pour répondre
  META_APP_SECRET      la clé secrète de l'app Meta, pour vérifier la signature
  ANTHROPIC_API_KEY    Claude
  DEEPSEEK_API_KEY     le modèle de secours
  ELEVENLABS_API_KEY   facultatif : écouter les vocaux et répondre de vive voix
  JWT_VERIFICATION_KEY facultatif : ouvre l'API d'AgentOS, protégée par jeton (console, mode 2)
  INTERNE_TOKEN        le jeton des routes internes (posé par la porte, propre à chaque client)
  MEGGA_INSTALLATION   « client » : installation chez le client (webhook direct, rappels sans porte,
                       licence exigée) ; sinon, derrière la porte de MEGGA
  META_VERIFY_TOKEN    chez le client : le jeton d'abonnement du webhook de Meta
  MEGGA_LICENCE        chez le client : la licence signée par MEGGA (noyau/licence.py)
Chaque secret peut aussi venir d'un fichier : <NOM>_FILE (noyau/environnement.py).

  PILOTAGE             le réglage du pilotage chez le client (non, suivi, complet), le même que celui du pilote

Avec PILOTAGE à suivi ou complet, la configuration servie est la dernière poussée par MEGGA et acceptée
(noyau/pilotage.py), revérifiée au démarrage, sinon CLIENT_CONFIG ; avec non, toujours CLIENT_CONFIG.
Quand le pilote en note une autre, l'agent finit ses tours et s'arrête : Compose ou Kubernetes le
relancent, et il la relit.

Routes :
  GET  /sante     l'état du conteneur, sans rien de privé
  GET  /whatsapp  l'abonnement du webhook de Meta (chez le client ; chez MEGGA, la porte s'en charge)
  POST /whatsapp  un webhook de Meta, transmis tel quel (corps et signature) ; sans numéro configuré, 404
  POST /api/messages  un logiciel parle à l'agent (clé du logiciel, noyau/api.py et docs/api.md)
  GET  /interne/cles             les clés des logiciels, sans empreinte (jeton INTERNE_TOKEN)
  POST /interne/cles             {id, logiciel, empreinte, par_minute} une clé créée par l'atelier
  DELETE /interne/cles/{id}      retire une clé
  POST /interne/rappels  envoie les rappels échus, rend l'heure du prochain (jeton INTERNE_TOKEN)
  POST /interne/vider    attend la fin des tours en cours, avant un redémarrage (jeton INTERNE_TOKEN)
  GET  /interne/suivi[?depuis=]                 volumes, modèles, échecs (jeton INTERNE_TOKEN)
  GET  /interne/suivi/conversations[?limite=]   les personnes qui ont écrit
  GET  /interne/suivi/conversations/{personne}  ses derniers messages, reçus et envoyés
  GET  /interne/suivi/alertes[?depuis=]         les échecs récents
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
import os
import signal
import time
from collections import OrderedDict

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from . import api as entree_api
from . import config as configuration
from . import licence as licences
from . import pilotage as pilotages
from . import stockage
from . import suivi as suivi_agent
from . import version as version_image
from .agent import construire, modele
from .environnement import charger
from .oral import consignes as consignes_orales
from .rappels import outils as outils_rappels
from .tour import EXCUSE, Conversations, en_echec  # noqa: F401 (EXCUSE et en_echec réexportés)
from .voix import Voie
from .whatsapp import Expediteur, SansWhatsApp, lire_entrants, signature_valide

log = logging.getLogger("megga")
CLES = ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY")


class Deja:
    """Les identifiants de messages déjà traités : Meta renvoie un webhook en cas de doute."""

    def __init__(self, taille: int = 2000):
        self._vus: OrderedDict[str, None] = OrderedDict()
        self._taille = taille

    def nouveau(self, ident: str) -> bool:
        if not ident:
            return True
        if ident in self._vus:
            return False
        self._vus[ident] = None
        if len(self._vus) > self._taille:
            self._vus.popitem(last=False)
        return True


def outils_du_client(conf, rappels) -> list:
    """Les outils du noyau (rappels) et ceux des packs que la configuration active."""
    liste = outils_rappels(rappels, conf.fuseau)
    if "immobilier" in conf.outils:
        from packs.immobilier import Catalogue, outils as outils_immobilier

        if not conf.catalogue:
            raise RuntimeError("pack immobilier sans catalogue")
        liste += outils_immobilier(Catalogue(conf.catalogue))
    return liste


def _reecriture(conf, cles):
    """Le modèle qui réécrit une réponse pour l'oral : un agent sans mémoire ni outils."""
    from agno.agent import Agent

    nom = conf.modeles.oral or conf.modeles.secours or conf.modeles.principal
    oral = Agent(model=modele(nom, cles), instructions=consignes_orales(conf), telemetry=False, markdown=False)

    async def reecrire(demande: str) -> str:
        sortie = await oral.arun(demande)
        if en_echec(sortie):
            raise RuntimeError("réécriture en échec")
        return getattr(sortie, "content", "") or ""

    return reecrire


def creer(env: dict[str, str] | None = None, agent=None, expediteur=None, voie=None, contacts=None,
          reecrire=None, attente: float = 2.5, seuil_regard: float = 8.0, rappels=None,
          delai_vider: float = 100.0, journal=None, lecture=None, fil=None, cle_licence=None, cle_pilotage=None,
          quitter=None, cles_api=None) -> FastAPI:
    """Les arguments nommés remplacent les vrais services (essais) ; `cle_licence` et `cle_pilotage`, les clés
    publiques des licences et des ordres de MEGGA ; `quitter`, l'arrêt de l'agent pour relire sa configuration."""
    env = charger(dict(os.environ if env is None else env))
    os.environ.setdefault("AGNO_TELEMETRY", "false")
    source = env.get("CLIENT_CONFIG") or env.get("CLIENT_CONFIG_FILE")
    if not source:
        raise RuntimeError("CLIENT_CONFIG manquante")
    fichier = configuration.lire(source)
    chez_le_client = env.get("MEGGA_INSTALLATION") == "client"
    # Le pilotage est le choix du client : avec « non », MEGGA ne change rien, même ce qu'il avait poussé.
    pilotage_actif = (env.get("PILOTAGE") or "non").strip().lower() in ("suivi", "complet")
    url = env.get("DATABASE_URL", "")
    # Chez le client, pas de licence valide, pas de démarrage (vérifiée sans appel extérieur), avant de toucher
    # à la base ; une configuration poussée garde l'identifiant du fichier (noyau/pilotage.py, config_de).
    licence = licences.verifier(env.get("MEGGA_LICENCE", ""), fichier.id, cle=cle_licence) if chez_le_client else None
    if agent is None:
        if not url:
            raise RuntimeError("DATABASE_URL manquante")
        stockage.migrer(url)  # avant toute table : une base neuve se reconnaît à ce qu'elle n'en a aucune
    # La dernière configuration poussée par MEGGA et acceptée, revérifiée ; sinon le fichier.
    ordres = stockage.Ordres(url) if pilotage_actif and url else None
    conf, pilotee, refus = fichier, None, None
    if ordres is not None:
        conf, pilotee, refus = pilotages.configuration_servie(fichier, ordres.a_servir(fichier.id), cle_pilotage)
        if refus:
            log.error("configuration poussée refusée (%s) : l'agent sert son fichier", refus)
    cles = {k: env.get(k, "") for k in CLES}
    quitter = quitter or (lambda: os.kill(os.getpid(), signal.SIGTERM))
    if agent is None:
        rappels = rappels or stockage.Rappels(env["DATABASE_URL"])
        agent = construire(conf, stockage.base_agno(env["DATABASE_URL"]), cles, outils=outils_du_client(conf, rappels))
        reecrire = reecrire or _reecriture(conf, cles)
    if env.get("DATABASE_URL"):
        journal = journal or stockage.Journal(env["DATABASE_URL"])
        lecture = lecture or stockage.Suivi(env["DATABASE_URL"])
        fil = fil or stockage.Fil(env["DATABASE_URL"])
        contacts = contacts or stockage.Contacts(env["DATABASE_URL"])
        cles_api = cles_api or stockage.ClesApi(env["DATABASE_URL"])
    if expediteur is None:
        expediteur = (Expediteur(env.get("META_TOKEN", ""), conf.whatsapp.numero_id, conf.whatsapp.version_graph)
                      if conf.whatsapp else SansWhatsApp())
    if voie is None and env.get("ELEVENLABS_API_KEY"):
        voie = Voie(env["ELEVENLABS_API_KEY"], conf.voix)
    conversations = Conversations(conf, agent, expediteur, voie, contacts, reecrire, attente, seuil_regard, rappels=rappels,
                                  journal=journal, fil=fil)
    jeton_interne = env.get("INTERNE_TOKEN", "")
    secret = env.get("META_APP_SECRET")
    deja = Deja()
    debit_cles = entree_api.DebitCles()

    def licence_echue() -> bool:
        """Au-delà du délai de grâce, même un agent lancé avant cesse de servir (vérifié à chaque appel)."""
        return bool(licence) and licences.etat_du_jour(licence)["etat"] == "hors_delai"

    async def finir_les_tours(delai: float) -> int:
        """Attend la fin des tours en cours (un tour peut en lancer un autre) ; rend ceux qui restent."""
        fin = time.monotonic() + delai
        while conversations.taches and time.monotonic() < fin:
            await asyncio.wait(set(conversations.taches), timeout=fin - time.monotonic())
        return len(conversations.taches)

    @contextlib.asynccontextmanager
    async def vie(_):
        arret = asyncio.Event()
        # Chez le client, pas de porte pour réveiller l'agent à l'heure d'un rappel ni pour le relancer
        # sur une nouvelle configuration : il veille lui-même.
        veille = asyncio.create_task(veiller(arret)) if (chez_le_client and rappels is not None) or ordres is not None else None
        yield
        # L'arrêt (SIGTERM : mise à jour, redémarrage) : ce qui est en route va au bout. La veille finit
        # sa tournée de rappels (un rappel envoyé est aussi marqué), puis les tours en cours se terminent.
        arret.set()
        if veille:
            await asyncio.wait({veille}, timeout=delai_vider)
        restantes = await finir_les_tours(delai_vider)
        if restantes:
            log.warning("arrêt avec %d tour(s) inachevé(s)", restantes)

    def a_relire() -> bool:
        """Une autre configuration est à servir : poussée et acceptée, retirée par le client, ou la précédente
        après un échec. Comparée par le numéro de son ordre (aucun : le fichier)."""
        _, nouvelle, _ = pilotages.configuration_servie(fichier, ordres.a_servir(fichier.id), cle_pilotage)
        return (nouvelle or {}).get("ordre") != (pilotee or {}).get("ordre")

    async def veiller(arret: asyncio.Event):
        verifier_le = 0.0
        while not arret.is_set():
            prochain = None
            if chez_le_client and rappels is not None and not licence_echue():
                try:
                    prochain = (await conversations.envoyer_rappels_echus(time.time())).get("prochain")
                except Exception as e:
                    log.error("rappels en échec : %s", str(e)[:200])
            if ordres is not None and time.monotonic() >= verifier_le:
                verifier_le = time.monotonic() + 30
                try:
                    if await asyncio.to_thread(a_relire):
                        # L'arrêt en douceur (SIGTERM) : les tours en cours finissent, puis Compose ou
                        # Kubernetes relancent l'agent, qui relit sa configuration.
                        log.info("nouvelle configuration du pilotage : l'agent finit ses tours et redémarre")
                        quitter()
                        return
                except Exception as e:
                    log.error("pilotage illisible : %s", str(e)[:200])
            attente = min(60.0, max(1.0, (prochain - time.time()) if prochain else 60.0))
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(arret.wait(), timeout=attente)

    app = FastAPI(title=f"megga-agents {conf.id}", docs_url=None, redoc_url=None, openapi_url=None, lifespan=vie)
    app.state.config = conf
    app.state.conversations = conversations
    app.state.taches = conversations.taches

    @app.get("/sante")
    async def sante():
        etat = {"ok": True, "client": conf.id, "zone": conf.zone, **version_image.carte(),
                "installation": "client" if chez_le_client else "megga"}
        if licence:
            etat["licence"] = licences.etat_du_jour(licence)
        if chez_le_client or ordres is not None:  # d'où vient la configuration servie : poussée par MEGGA (version, ordre), ou le fichier
            etat["configuration"] = {"source": "pilotage", **pilotee} if pilotee else {"source": "fichier"}
        if licence_echue():  # les sondes le voient : l'agent n'est plus en service
            return JSONResponse({**etat, "ok": False}, status_code=503)
        return etat

    @app.get("/whatsapp")
    async def abonnement(requete: Request):
        """Meta vérifie l'adresse du webhook : le défi est rendu si le jeton correspond."""
        if conf.whatsapp is None:
            return Response("pas de WhatsApp", status_code=404)
        p = requete.query_params
        jeton = env.get("META_VERIFY_TOKEN", "")
        # En octets : un jeton accentué se compare aussi (sur des textes, compare_digest n'accepte que l'ASCII).
        if jeton and p.get("hub.mode") == "subscribe" and hmac.compare_digest(p.get("hub.verify_token", "").encode(), jeton.encode()):
            return Response(p.get("hub.challenge", ""), media_type="text/plain")
        return Response("refusé", status_code=403)

    @app.post("/whatsapp")
    async def whatsapp(requete: Request):
        if licence_echue():
            return Response("licence échue", status_code=503)
        if conf.whatsapp is None:
            return Response("pas de WhatsApp", status_code=404)
        corps = await requete.body()
        if not signature_valide(corps, requete.headers.get("x-hub-signature-256"), secret):
            return Response("signature", status_code=401)
        try:
            evenement = json.loads(corps)
        except ValueError:
            return Response("corps", status_code=400)
        lus = 0
        for m in lire_entrants(evenement, conf.whatsapp.numero_id):
            if not m.frais():
                log.warning("message ancien, sans réponse")
                continue
            if not deja.nouveau(m.id):
                continue
            conversations.recevoir(m)
            lus += 1
        # Meta veut une réponse rapide : le tour se poursuit après.
        return Response(f"reçu {lus}", media_type="text/plain")

    def erreur(statut: int, message: str, entetes: dict | None = None, **autres) -> JSONResponse:
        return JSONResponse({"erreur": message, **autres}, status_code=statut, headers=entetes)

    @app.post("/api/messages")
    async def api_messages(requete: Request):
        """Un logiciel parle à l'agent : la réponse vient dans la même requête (noyau/api.py, docs/api.md)."""
        if licence_echue():
            return erreur(503, "licence échue")
        if cles_api is None:
            return erreur(503, "entrée par API indisponible")
        jeton = (requete.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        cle = await asyncio.to_thread(cles_api.par_empreinte, entree_api.empreinte(jeton)) if entree_api.CLE.fullmatch(jeton) else None
        if cle is None:
            return erreur(401, "clé refusée")
        # Lu par morceaux, borné : un corps trop gros est refusé sans être gardé en mémoire.
        corps = bytearray()
        async for morceau in requete.stream():
            corps += morceau
            if len(corps) > entree_api.CORPS_MAX:
                return erreur(413, "requête trop grosse")
        try:
            donnees = json.loads(bytes(corps))
        except ValueError:
            return erreur(400, "corps : du JSON")
        if not isinstance(donnees, dict) or set(donnees) - {"personne", "texte"}:
            return erreur(400, "corps : {personne, texte}")
        personne, texte = donnees.get("personne"), donnees.get("texte")
        if not isinstance(personne, str) or not entree_api.IDENTIFIANT.fullmatch(personne):
            return erreur(400, "personne : un identifiant de 1 à 40 caractères (lettres, chiffres, . _ -), avec au moins une lettre ; jamais un numéro de téléphone")
        if not isinstance(texte, str) or not texte.strip() or len(texte) > entree_api.TEXTE_MAX:
            return erreur(400, f"texte : de 1 à {entree_api.TEXTE_MAX} caractères")
        if not debit_cles.permis(cle):
            conversations._noter_journal("api_debit", detail=cle["id"])
            attente = debit_cles.attente(cle)
            return erreur(429, "trop de messages pour cette clé", attente=attente, entetes={"retry-after": str(attente)})
        tour = await conversations.repondre_api(entree_api.personne_interne(cle["logiciel"], personne), texte.strip())
        if tour is None:
            conversations._noter_journal("api_debit", detail="personne")
            return erreur(429, "trop de messages pour cette personne", attente=60, entetes={"retry-after": "60"})
        reponse, echec = tour
        if echec:  # le tour a échoué : le logiciel peut réessayer, ou montrer l'excuse
            return erreur(503, "l'agent n'a pas pu répondre", reponse=reponse)
        return {"reponse": reponse}

    def interne(requete: Request) -> bool:
        jeton = requete.headers.get("x-megga-interne", "")
        return bool(jeton_interne) and hmac.compare_digest(jeton.encode(), jeton_interne.encode())

    @app.post("/interne/rappels")
    async def interne_rappels(requete: Request):
        if not interne(requete):
            return Response("refusé", status_code=401)
        return await conversations.envoyer_rappels_echus(time.time())

    @app.post("/interne/vider")
    async def interne_vider(requete: Request):
        if not interne(requete):
            return Response("refusé", status_code=401)
        return {"restantes": await finir_les_tours(delai_vider)}

    def lisible(requete: Request) -> Response | None:
        if not interne(requete):
            return Response("refusé", status_code=401)
        if lecture is None or journal is None or fil is None:
            return Response("suivi indisponible", status_code=503)
        return None

    def borne(valeur: str | None, defaut: int, maximum: int) -> int:
        try:
            return max(1, min(int(valeur or defaut), maximum))
        except ValueError:
            return defaut

    def date(valeur: str | None) -> float:
        try:
            return max(0.0, float(valeur or 0))
        except ValueError:
            return 0.0

    @app.get("/interne/suivi")
    async def interne_suivi(requete: Request):
        if (refus := lisible(requete)) is not None:
            return refus
        depuis = date(requete.query_params.get("depuis"))
        tours = await asyncio.to_thread(lecture.tours, depuis)
        totaux = await asyncio.to_thread(journal.totaux, depuis)
        attente = await asyncio.to_thread(rappels.en_attente) if rappels is not None else 0
        return suivi_agent.resumer(conf, tours, totaux, attente, depuis)

    @app.get("/interne/suivi/conversations")
    async def interne_conversations(requete: Request):
        if (refus := lisible(requete)) is not None:
            return refus
        limite = borne(requete.query_params.get("limite"), 50, 200)
        # Le fil d'abord ; les tours d'Agno pour les conversations d'avant le fil.
        source = lecture if await asyncio.to_thread(fil.vide) else fil
        return {"conversations": await asyncio.to_thread(source.conversations, limite)}

    @app.get("/interne/suivi/conversations/{personne}")
    async def interne_echanges(personne: str, requete: Request):
        if (refus := lisible(requete)) is not None:
            return refus
        if not suivi_agent.PERSONNE.fullmatch(personne):
            return Response("personne", status_code=400)
        limite = borne(requete.query_params.get("limite"), 50, 200)
        messages = await asyncio.to_thread(fil.messages, personne, limite)
        if not messages:
            messages = await asyncio.to_thread(lecture.messages, personne, limite, EXCUSE)
        return {"personne": personne, "messages": [suivi_agent.message_lisible(m) for m in messages]}

    @app.get("/interne/suivi/alertes")
    async def interne_alertes(requete: Request):
        if (refus := lisible(requete)) is not None:
            return refus
        return {"alertes": await asyncio.to_thread(journal.alertes, date(requete.query_params.get("depuis")))}

    def cles_lisibles(requete: Request) -> Response | None:
        if not interne(requete):
            return Response("refusé", status_code=401)
        if cles_api is None:
            return Response("base absente", status_code=503)
        return None

    @app.get("/interne/cles")
    async def interne_cles(requete: Request):
        if (refus := cles_lisibles(requete)) is not None:
            return refus
        return {"cles": await asyncio.to_thread(cles_api.lister)}

    @app.post("/interne/cles")
    async def interne_ajouter_cle(requete: Request):
        """Une clé créée par l'atelier : son empreinte seulement, la clé ne vient jamais jusqu'ici."""
        if (refus := cles_lisibles(requete)) is not None:
            return refus
        try:
            d = await requete.json()
            ident, logiciel, empreinte = d["id"], d["logiciel"], d["empreinte"]
            debit = entree_api.par_minute(d.get("par_minute"))
        except (ValueError, KeyError, TypeError):
            return erreur(400, "{id, logiciel, empreinte, par_minute}")
        if not (isinstance(ident, str) and entree_api.IDENT_CLE.fullmatch(ident) and isinstance(logiciel, str)
                and entree_api.LOGICIEL.fullmatch(logiciel) and isinstance(empreinte, str) and entree_api.EMPREINTE.fullmatch(empreinte)):
            return erreur(400, "{id, logiciel, empreinte, par_minute}")
        if not await asyncio.to_thread(cles_api.ajouter, ident, logiciel, empreinte, debit):
            return erreur(409, "clé déjà enregistrée")
        return {"id": ident, "logiciel": logiciel, "par_minute": debit}

    @app.delete("/interne/cles/{ident}")
    async def interne_retirer_cle(ident: str, requete: Request):
        if (refus := cles_lisibles(requete)) is not None:
            return refus
        if not entree_api.IDENT_CLE.fullmatch(ident):
            return erreur(400, "identifiant de clé")
        return {"id": ident, "retiree": await asyncio.to_thread(cles_api.retirer, ident)}

    if env.get("JWT_VERIFICATION_KEY"):
        from agno.os import AgentOS

        os.environ.setdefault("JWT_VERIFICATION_KEY", env["JWT_VERIFICATION_KEY"])
        return AgentOS(agents=[agent], base_app=app, authorization=True, telemetry=False).get_app()
    return app


def principal() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(creer(), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), access_log=False)
