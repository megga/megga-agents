"""L'API de l'atelier. Pas d'écran : l'interface viendra au dernier lot et ne fera que l'appeler.

Variables d'environnement (jamais dans le dépôt) :
  DATABASE_URL       la base de l'atelier (versions des configurations, jetons des clients)
  ADMIN_TOKEN        le jeton de MEGGA (le même que celui de la porte)
  PORTE_URL          l'adresse de la porte, pour l'annuaire et les conteneurs
  ANTHROPIC_API_KEY, DEEPSEEK_API_KEY   les modèles, pour le mode d'essai
  ESSAIS_DIR         facultatif : le dossier des bases d'essai

Rôles, par le jeton (Authorization: Bearer …) :
  MEGGA   ADMIN_TOKEN : tous les clients, tous les réglages
  client  un jeton délivré par MEGGA : son seul agent, les réglages simples

Routes (toutes sous /atelier) :
  GET   /catalogue                              métiers, outils, zones, modèles, réglages du client
  GET   /gabarits                               les modèles par métier, prêts à marcher
  GET   /clients                                les clients et leur état (MEGGA : tous ; client : le sien) ;
                                                « ecart » : l'annuaire de la porte ne sert pas la version en service
  POST  /clients                                MEGGA : un nouveau client, d'une configuration complète
                                                ou d'un modèle par métier (gabarit, identité, prénom)
  GET   /clients/{id}                           un client, sa version en service et sa configuration
  GET   /clients/{id}/versions                  l'historique
  GET   /clients/{id}/versions/{v}              une version et sa configuration
  POST  /clients/{id}/valider                   valide des changements sans rien enregistrer
  POST  /clients/{id}/versions                  une nouvelle version (brouillon), d'après une base
  POST  /clients/{id}/gabarit                   une nouvelle version d'après un modèle par métier et un prénom
  POST  /clients/{id}/versions/{v}/essai        l'agent de cette version répond, hors WhatsApp
  POST  /clients/{id}/versions/{v}/activer      mise en service (ou retour à une version publiée)
  POST  /clients/{id}/reprise                   MEGGA : reprendre la main (ou la rendre)
  POST  /clients/{id}/jetons                    MEGGA : un jeton pour le client, montré une fois
  DELETE /clients/{id}/jetons                   MEGGA : retire tous les jetons du client

Suivi (lu dans le conteneur du client, qui se réveille s'il dormait) :
  GET   /clients/{id}/suivi[?jours=7]           état, activité (tours, personnes, modèles, voix) ;
                                                coûts pour MEGGA seulement
  GET   /clients/{id}/conversations[?limite=]   les personnes qui ont écrit
  GET   /clients/{id}/conversations/{personne}  les derniers échanges avec elle
  GET   /clients/{id}/alertes[?jours=7]         échecs, pannes du conteneur, écart avec l'annuaire
  GET   /tarifs, PUT /tarifs                    MEGGA : les tarifs des modèles et de la voix
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import re
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Body, Depends, FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from noyau import stockage
from noyau.app import CLES
from noyau.config import Config
from noyau.suivi import PERSONNE

from . import gabarits, regles
from .couts import Tarifs, couts
from .essai import essayer
from .porte import Porte, PorteErreur
from .regles import Refus
from .versions import Versions

log = logging.getLogger("megga.atelier")
ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
CONVERSATION = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


@dataclass(frozen=True)
class Identite:
    role: str  # « megga » ou « client »
    client: str | None = None


async def bd(f, *a, **k):
    """Un appel à la base, hors de la boucle : une lecture lente ne gèle pas les autres requêtes."""
    return await run_in_threadpool(f, *a, **k)


def creer(env: dict[str, str] | None = None, db=None, porte=None, principal_essai=None) -> FastAPI:
    """Les arguments nommés remplacent les vrais services (essais du code)."""
    env = dict(os.environ if env is None else env)
    os.environ.setdefault("AGNO_TELEMETRY", "false")
    admin = env.get("ADMIN_TOKEN", "")
    if not admin:
        raise RuntimeError("ADMIN_TOKEN manquant")
    if not env.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL manquante")
    versions = Versions(db if db is not None else stockage.base_agno(env["DATABASE_URL"]))
    jetons = stockage.Jetons(env["DATABASE_URL"])
    reglages = stockage.Reglages(env["DATABASE_URL"])
    if porte is None and env.get("PORTE_URL"):
        porte = Porte(env["PORTE_URL"], admin)
    cles = {k: env.get(k, "") for k in CLES}
    essais = Path(env.get("ESSAIS_DIR") or Path(tempfile.gettempdir()) / "megga-essais")
    # Une mise en service à la fois par client (l'atelier est un seul processus).
    verrous: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def identite(requete: Request) -> Identite:
        jeton = (requete.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        if jeton and hmac.compare_digest(jeton.encode(), admin.encode()):
            return Identite("megga")
        client = jetons.client(jeton)
        if client:
            return Identite("client", client)
        raise Refus(401, "jeton refusé")

    def megga(qui: Identite) -> None:
        if qui.role != "megga":
            raise Refus(403, "réservé à MEGGA")

    def client_de(qui: Identite, ident: str) -> dict:
        """Le client, s'il existe et si ce rôle peut le voir (un client ne voit que le sien)."""
        if not ID.fullmatch(ident) or (qui.role == "client" and qui.client != ident):
            raise Refus(404, "client inconnu")
        c = versions.client(ident)
        if c is None:
            raise Refus(404, "client inconnu")
        return c

    def version_de(ident: str, numero: int) -> dict:
        v = versions.version(ident, numero)
        if v is None:
            raise Refus(404, "version inconnue")
        return v

    def resume(c: dict, derniere: int | None, etats: dict | None) -> dict:
        meta = c.get("metadata") or {}
        r = {
            "id": c["component_id"],
            "nom_agent": c.get("name"),
            "entreprise": c.get("description"),
            "version_en_service": c.get("current_version"),
            "derniere_version": derniere,
            "gere_par_megga": bool(meta.get("gere_par_megga")),
        }
        if etats is not None:
            a = etats.get(c["component_id"])
            r["annuaire"] = a
            # Une mise en service interrompue : la porte sert une autre version que l'atelier.
            r["ecart"] = a is not None and a.get("version") != c.get("current_version")
        return r

    async def etats_porte(ident: str | None = None) -> dict | None:
        if porte is None:
            return None
        try:
            return await porte.etats(ident)
        except PorteErreur as e:  # l'état de la porte n'empêche pas de lister
            log.warning("porte injoignable : %s", str(e)[:120])
            return None

    def zone_en_service(ident: str) -> str | None:
        v = versions.en_service(ident)
        return (v["config"] or {}).get("zone") if v else None

    def nouvelle(qui: Identite, ident: str, corps: dict) -> tuple[Config, int]:
        """La configuration d'une nouvelle version, d'après sa base (la dernière par défaut)."""
        base_n = regles.numero(corps.get("base"), "base")
        base = version_de(ident, base_n) if base_n is not None else versions.derniere(ident)
        if base is None:
            raise Refus(404, "aucune version de base")
        changements = corps.get("changements")
        conf = regles.appliquer(qui.role, base["config"], {} if changements is None else changements, zone_en_service(ident))
        return conf, base["version"]

    def preparer(qui: Identite, ident: str, corps: dict) -> tuple[Config, int]:
        client_de(qui, ident)
        return nouvelle(qui, ident, corps)

    def config_de(v: dict) -> Config:
        """La configuration d'une version, revalidée par le code en service ; complète."""
        conf = regles.valider(v["config"])
        if regles.manques(conf):
            raise Refus(409, "version incomplète", regles.manques(conf))
        return conf

    r = APIRouter(prefix="/atelier")

    @r.get("/catalogue")
    def catalogue(qui: Identite = Depends(identite)):
        return regles.catalogue()

    @r.get("/clients")
    async def lister(qui: Identite = Depends(identite)):
        if qui.role == "megga":
            tous, etats = await bd(versions.clients), await etats_porte()
        else:
            tous = [c for c in [await bd(versions.client, qui.client)] if c]
            etats = await etats_porte(qui.client)
        dernieres = await bd(versions.dernieres, {c["component_id"] for c in tous}) if tous else {}
        return {"clients": [resume(c, dernieres.get(c["component_id"]), etats) for c in tous], "porte": etats is not None}

    @r.get("/gabarits")
    def liste_gabarits(qui: Identite = Depends(identite)):
        return {"gabarits": gabarits.lister()}

    @r.post("/clients", status_code=201)
    def creer_client(qui: Identite = Depends(identite), corps: dict = Body(...)):
        megga(qui)
        if corps.get("gabarit") is not None:
            donnees = gabarits.nouvelle_config(corps["gabarit"], corps.get("client"), corps.get("nom_agent"))
        else:
            donnees = corps.get("config") or {}
        conf = regles.valider(donnees)
        if versions.db.get_component(conf.id, include_deleted=True) is not None:
            raise Refus(409, "ce client existe déjà")
        return {"client": conf.id, **versions.creer(conf, "megga")}

    @r.get("/clients/{ident}")
    async def lire(ident: str, qui: Identite = Depends(identite)):
        c = await bd(client_de, qui, ident)
        courante = c.get("current_version")
        config = (await bd(version_de, ident, courante))["config"] if courante else None
        derniere = (await bd(versions.dernieres, {ident})).get(ident)
        return {**resume(c, derniere, await etats_porte(ident)), "config": config}

    @r.get("/clients/{ident}/versions")
    def historique(ident: str, qui: Identite = Depends(identite)):
        client_de(qui, ident)
        return {"versions": versions.historique(ident)}

    @r.get("/clients/{ident}/versions/{numero}")
    def version(ident: str, numero: int, qui: Identite = Depends(identite)):
        client_de(qui, ident)
        return version_de(ident, numero)

    @r.post("/clients/{ident}/valider")
    def valider(ident: str, qui: Identite = Depends(identite), corps: dict = Body(...)):
        conf, base = preparer(qui, ident, corps)
        return {"base": base, "config": conf.model_dump(mode="json"), "manques": regles.manques(conf)}

    @r.post("/clients/{ident}/versions", status_code=201)
    def ajouter(ident: str, qui: Identite = Depends(identite), corps: dict = Body(...)):
        conf, base = preparer(qui, ident, corps)
        v = versions.ajouter(conf, qui.role, base)
        return {**v, "manques": regles.manques(conf)}

    @r.post("/clients/{ident}/gabarit", status_code=201)
    def depuis_gabarit(ident: str, qui: Identite = Depends(identite), corps: dict = Body(...)):
        """Un modèle par métier appliqué à ce client : son identité et les réglages de MEGGA restent."""
        client_de(qui, ident)
        base_n = regles.numero(corps.get("base"), "base")
        base = version_de(ident, base_n) if base_n is not None else versions.derniere(ident)
        if base is None:
            raise Refus(404, "aucune version de base")
        changements = gabarits.reglages_pour(corps.get("gabarit"), base["config"])
        if corps.get("nom_agent") is not None:
            changements["nom_agent"] = corps["nom_agent"]
        conf = regles.valider(regles.fusionner(base["config"], changements))
        regles.verifier_zone(conf, zone_en_service(ident))
        v = versions.ajouter(conf, qui.role, base["version"])
        return {**v, "gabarit": corps["gabarit"], "manques": regles.manques(conf)}

    @r.post("/clients/{ident}/versions/{numero}/essai")
    async def essai(ident: str, numero: int, qui: Identite = Depends(identite), corps: dict = Body(...)):
        await bd(client_de, qui, ident)
        v = await bd(version_de, ident, numero)
        message = corps.get("message")
        if not isinstance(message, str) or not message.strip() or len(message) > 4000:
            raise Refus(400, "message : un texte de 1 à 4000 caractères")
        conversation = str(corps.get("conversation") or "1")
        if not CONVERSATION.fullmatch(conversation):
            raise Refus(400, "conversation : lettres, chiffres, - et _")
        conf = config_de(v)
        reponse = await essayer(conf, numero, message, conversation, cles, essais, principal=principal_essai)
        await bd(versions.noter_essai, ident, numero)
        return {"version": numero, "conversation": conversation, "reponse": reponse}

    @r.post("/clients/{ident}/versions/{numero}/activer")
    async def activer(ident: str, numero: int, qui: Identite = Depends(identite), corps: dict | None = Body(None)):
        forcer = regles.oui_non((corps or {}).get("forcer"), False, "forcer")
        async with verrous[ident]:
            c = await bd(client_de, qui, ident)
            v = await bd(version_de, ident, numero)
            if qui.role == "client":
                if (c.get("metadata") or {}).get("gere_par_megga"):
                    raise Refus(403, "MEGGA a repris la main sur cet agent : la mise en service passe par MEGGA")
                if forcer:
                    raise Refus(403, "forcer : réservé à MEGGA")
            courante = c.get("current_version")
            if courante == numero:
                raise Refus(409, "cette version est déjà en service")
            if v["etat"] == "brouillon" and v["essais"] == 0 and not forcer:
                raise Refus(409, "essayez d'abord cette version (mode d'essai)")
            conf = config_de(v)
            avant = await bd(version_de, ident, courante) if courante else None
            regles.verifier_zone(conf, (avant["config"] or {}).get("zone") if avant else None)
            par_porte = conf.zone in regles.ZONES_PORTE
            if par_porte:
                if porte is None:
                    raise Refus(503, "porte non réglée (PORTE_URL)")
                try:
                    annuaire = await porte.activer(conf, numero)
                except PorteErreur as e:
                    if e.statut == 0:
                        raise Refus(504, "la porte n'a pas répondu : vérifiez l'écart dans la liste des clients avant de relancer",
                                    {"texte": e.texte}) from e
                    raise Refus(502, "la porte a refusé la mise en service", {"statut": e.statut, "texte": e.texte}) from e
            else:
                # Suisse et installation chez le client : poussée par le pilotage (lot 6).
                annuaire = {"zone": conf.zone, "porte": False}
            try:
                await bd(versions.mettre_en_service, ident, numero, courante)
            except Exception as e:
                # L'annuaire sert déjà la nouvelle version : on le remet sur celle d'avant.
                log.error("mise en service de %s v%s interrompue : %s", ident, numero, str(e)[:200])
                retabli = False
                if par_porte and avant is not None:
                    try:
                        await porte.activer(regles.valider(avant["config"]), courante)
                        retabli = True
                    except (PorteErreur, Refus):
                        pass
                raise Refus(500, "mise en service interrompue", {"annuaire_retabli": retabli}) from e
        return {"client": ident, "version_en_service": numero, "retour": v["etat"] == "publiee", "annuaire": annuaire}

    @r.post("/clients/{ident}/reprise")
    def reprise(ident: str, qui: Identite = Depends(identite), corps: dict = Body(...)):
        megga(qui)
        client_de(qui, ident)
        meta = versions.regler(ident, gere_par_megga=regles.oui_non(corps.get("gere_par_megga"), True, "gere_par_megga"))
        return {"client": ident, "gere_par_megga": meta["gere_par_megga"]}

    @r.post("/clients/{ident}/jetons", status_code=201)
    def jeton(ident: str, qui: Identite = Depends(identite)):
        megga(qui)
        client_de(qui, ident)
        return {"client": ident, "jeton": jetons.creer(ident)}

    @r.delete("/clients/{ident}/jetons")
    def revoquer(ident: str, qui: Identite = Depends(identite)):
        megga(qui)
        client_de(qui, ident)
        return {"client": ident, "retires": jetons.revoquer(ident)}

    # Le suivi

    def jours_de(valeur: str | None) -> int:
        try:
            jours = int(valeur or 7)
        except ValueError:
            raise Refus(400, "jours : un nombre de 1 à 365") from None
        if not 1 <= jours <= 365:
            raise Refus(400, "jours : un nombre de 1 à 365")
        return jours

    def limite_de(valeur: str | None) -> int | None:
        if valeur is None:
            return None
        if not valeur.isdigit() or not 1 <= int(valeur) <= 200:
            raise Refus(400, "limite : un nombre de 1 à 200")
        return int(valeur)

    def suivable(qui: Identite, ident: str) -> dict:
        """Le client, si son suivi passe par la porte (zones Europe et États-Unis)."""
        c = client_de(qui, ident)
        v = versions.en_service(ident) or versions.derniere(ident)
        zone = ((v or {}).get("config") or {}).get("zone")
        if zone not in regles.ZONES_PORTE:
            raise Refus(409, "suivi hors porte (zone suisse ou chez le client) : il viendra avec le pilotage, au lot 6")
        if porte is None:
            raise Refus(503, "porte non réglée (PORTE_URL)")
        return c

    def raison(e: PorteErreur) -> str:
        """Ce qui a empêché la lecture, dit simplement."""
        if e.statut == 0:
            return "la porte n'a pas répondu"
        if e.statut == 401:
            return "le conteneur refuse la lecture (jeton interne : le jeton d'administration a-t-il changé ?)"
        try:
            erreur = json.loads(e.texte).get("erreur")
        except (ValueError, AttributeError):
            erreur = None
        if erreur == "conteneur injoignable":
            return "le conteneur du client ne répond pas"
        if erreur == "suivi indisponible" or "suivi indisponible" in e.texte:
            return "le conteneur répond, mais sa base n'est pas branchée"
        return f"réponse inattendue du conteneur ({e.statut})"

    async def lire_suivi(ident: str, chemin: str = "", **params) -> dict:
        try:
            return await porte.suivi(ident, chemin, **params)
        except PorteErreur as e:
            if e.statut in (400, 404):
                raise Refus(e.statut, "suivi refusé", {"texte": e.texte}) from e
            raise Refus(502 if e.statut else 504, f"suivi indisponible : {raison(e)}",
                        {"statut": e.statut, "texte": e.texte}) from e

    def debut(jours: int) -> int:
        """Le début de la période, arrondi à 5 minutes : des lectures rapprochées tombent sur la lecture
        gardée en mémoire par la porte, sans réveiller le conteneur du client."""
        return int((time.time() - jours * 86400) // 300 * 300)

    def lire_tarifs() -> Tarifs:
        return Tarifs.model_validate(reglages.lire("tarifs") or {})

    @r.get("/clients/{ident}/suivi")
    async def suivi(ident: str, requete: Request, qui: Identite = Depends(identite)):
        jours = jours_de(requete.query_params.get("jours"))
        c = await bd(suivable, qui, ident)
        derniere = (await bd(versions.dernieres, {ident})).get(ident)
        etats = await etats_porte(ident)
        activite = await lire_suivi(ident, depuis=debut(jours))
        sortie = {**resume(c, derniere, etats), "periode_jours": jours, "activite": activite}
        if qui.role == "megga":
            sortie["couts"] = couts(activite, await bd(lire_tarifs))
        return sortie

    @r.get("/clients/{ident}/conversations")
    async def conversations(ident: str, requete: Request, qui: Identite = Depends(identite)):
        limite = limite_de(requete.query_params.get("limite"))
        await bd(suivable, qui, ident)
        return await lire_suivi(ident, "/conversations", limite=limite)

    @r.get("/clients/{ident}/conversations/{personne}")
    async def echanges(ident: str, personne: str, requete: Request, qui: Identite = Depends(identite)):
        limite = limite_de(requete.query_params.get("limite"))
        if not PERSONNE.fullmatch(personne):
            raise Refus(400, "personne : un numéro")
        await bd(suivable, qui, ident)
        return await lire_suivi(ident, f"/conversations/{personne}", limite=limite)

    @r.get("/clients/{ident}/alertes")
    async def alertes(ident: str, requete: Request, qui: Identite = Depends(identite)):
        jours = jours_de(requete.query_params.get("jours"))
        c = await bd(suivable, qui, ident)
        maintenant = time.time()
        depuis = debut(jours)
        liste = []
        etats = await etats_porte(ident)
        if etats is None:
            liste.append({"quand": maintenant, "genre": "porte_injoignable", "detail": ""})
        else:
            a = etats.get(ident) or {}
            if a and a.get("version") != c.get("current_version"):
                liste.append({"quand": maintenant, "genre": "ecart",
                              "detail": f"l'annuaire sert la version {a.get('version')}, l'atelier la {c.get('current_version')}"})
            for panne in (a.get("conteneur") or {}).get("alertes") or []:
                if panne.get("quand", 0) / 1000 >= depuis:
                    resolue = panne.get("resolue")
                    liste.append({"quand": panne["quand"] / 1000, "genre": f"conteneur_{panne.get('quoi')}",
                                  "detail": panne.get("message", ""), "resolue": resolue / 1000 if resolue else None})
        try:
            liste += (await lire_suivi(ident, "/alertes", depuis=depuis)).get("alertes", [])
        except Refus as e:
            liste.append({"quand": maintenant, "genre": "conteneur_injoignable", "detail": e.message})
        return {"periode_jours": jours, "alertes": sorted(liste, key=lambda x: x["quand"], reverse=True)}

    @r.get("/tarifs")
    def tarifs(qui: Identite = Depends(identite)):
        megga(qui)
        return lire_tarifs().model_dump()

    @r.put("/tarifs")
    def regler_tarifs(qui: Identite = Depends(identite), corps: dict = Body(...)):
        megga(qui)
        try:
            t = Tarifs.model_validate(corps)
        except ValidationError as e:
            raise Refus(422, "tarifs invalides", regles.erreurs(e)) from e
        reglages.ecrire("tarifs", t.model_dump())
        return t.model_dump()

    app = FastAPI(title="megga-atelier", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.versions = versions
    app.state.jetons = jetons

    @app.exception_handler(Refus)
    async def refus(_: Request, e: Refus):
        corps = {"erreur": e.message}
        if e.details is not None:
            corps["details"] = e.details
        return JSONResponse(corps, status_code=e.statut)

    @app.get("/sante")
    async def sante():
        return {"ok": True, "service": "atelier"}

    app.include_router(r)
    return app


def principal() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(creer(), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), access_log=False)
