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
  GET   /clients                                les clients et leur état (MEGGA : tous ; client : le sien)
  POST  /clients                                MEGGA : un nouveau client, d'une configuration complète
  GET   /clients/{id}                           un client, sa version en service et sa configuration
  GET   /clients/{id}/versions                  l'historique
  GET   /clients/{id}/versions/{v}              une version et sa configuration
  POST  /clients/{id}/valider                   valide des changements sans rien enregistrer
  POST  /clients/{id}/versions                  une nouvelle version (brouillon), d'après une base
  POST  /clients/{id}/versions/{v}/essai        l'agent de cette version répond, hors WhatsApp
  POST  /clients/{id}/versions/{v}/activer      mise en service (ou retour à une version publiée)
  POST  /clients/{id}/reprise                   MEGGA : reprendre la main (ou la rendre)
  POST  /clients/{id}/jetons                    MEGGA : un jeton pour le client, montré une fois
  DELETE /clients/{id}/jetons                   MEGGA : retire tous les jetons du client
"""

from __future__ import annotations

import hmac
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Body, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from noyau import stockage
from noyau.config import Config

from . import regles
from .essai import essayer
from .porte import Porte, PorteErreur
from .regles import Refus
from .versions import Versions

log = logging.getLogger("megga.atelier")
CLES = ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY")
ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
CONVERSATION = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


@dataclass(frozen=True)
class Identite:
    role: str  # « megga » ou « client »
    client: str | None = None


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
    if porte is None and env.get("PORTE_URL"):
        porte = Porte(env["PORTE_URL"], admin)
    cles = {k: env.get(k, "") for k in CLES}
    essais = Path(env.get("ESSAIS_DIR") or Path(tempfile.gettempdir()) / "megga-essais")

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

    def resume(c: dict, etats: dict | None) -> dict:
        meta = c.get("metadata") or {}
        derniere = versions.derniere(c["component_id"])
        r = {
            "id": c["component_id"],
            "nom_agent": c.get("name"),
            "entreprise": c.get("description"),
            "version_en_service": c.get("current_version"),
            "derniere_version": derniere["version"] if derniere else None,
            "gere_par_megga": bool(meta.get("gere_par_megga")),
        }
        if etats is not None:
            r["annuaire"] = etats.get(c["component_id"])
        return r

    async def etats_porte() -> dict | None:
        if porte is None:
            return None
        try:
            return await porte.etats()
        except Exception as e:  # l'état de la porte n'empêche pas de lister
            log.warning("porte injoignable : %s", str(e)[:120])
            return None

    def nouvelle(qui: Identite, ident: str, corps: dict) -> tuple[Config, int]:
        """La configuration d'une nouvelle version, d'après sa base (la dernière par défaut)."""
        base_n = corps.get("base")
        base = version_de(ident, int(base_n)) if base_n is not None else versions.derniere(ident)
        if base is None:
            raise Refus(404, "aucune version de base")
        conf = regles.appliquer(qui.role, base["config"], corps.get("changements") or {},
                                zone_figee=versions.courante(ident) is not None)
        return conf, base["version"]

    r = APIRouter(prefix="/atelier")

    @r.get("/catalogue")
    async def catalogue(qui: Identite = Depends(identite)):
        return regles.catalogue()

    @r.get("/clients")
    async def lister(qui: Identite = Depends(identite)):
        etats = await etats_porte()
        tous = versions.clients() if qui.role == "megga" else [c for c in [versions.client(qui.client)] if c]
        return {"clients": [resume(c, etats) for c in tous], "porte": etats is not None}

    @r.post("/clients", status_code=201)
    async def creer_client(qui: Identite = Depends(identite), corps: dict = Body(...)):
        megga(qui)
        try:
            conf = Config.model_validate(corps.get("config") or {})
        except ValidationError as e:
            raise Refus(422, "configuration invalide", regles.erreurs(e)) from e
        if versions.db.get_component(conf.id, include_deleted=True) is not None:
            raise Refus(409, "ce client existe déjà")
        return {"client": conf.id, **versions.creer(conf, "megga")}

    @r.get("/clients/{ident}")
    async def lire(ident: str, qui: Identite = Depends(identite)):
        c = client_de(qui, ident)
        etats = await etats_porte()
        courante = c.get("current_version")
        return {**resume(c, etats), "config": version_de(ident, courante)["config"] if courante else None}

    @r.get("/clients/{ident}/versions")
    async def historique(ident: str, qui: Identite = Depends(identite)):
        client_de(qui, ident)
        return {"versions": versions.historique(ident)}

    @r.get("/clients/{ident}/versions/{numero}")
    async def version(ident: str, numero: int, qui: Identite = Depends(identite)):
        client_de(qui, ident)
        return version_de(ident, numero)

    @r.post("/clients/{ident}/valider")
    async def valider(ident: str, qui: Identite = Depends(identite), corps: dict = Body(...)):
        client_de(qui, ident)
        conf, base = nouvelle(qui, ident, corps)
        return {"base": base, "config": conf.model_dump(mode="json"), "manques": regles.manques(conf)}

    @r.post("/clients/{ident}/versions", status_code=201)
    async def ajouter(ident: str, qui: Identite = Depends(identite), corps: dict = Body(...)):
        client_de(qui, ident)
        conf, base = nouvelle(qui, ident, corps)
        v = versions.ajouter(conf, qui.role, base)
        return {**v, "manques": regles.manques(conf)}

    @r.post("/clients/{ident}/versions/{numero}/essai")
    async def essai(ident: str, numero: int, qui: Identite = Depends(identite), corps: dict = Body(...)):
        client_de(qui, ident)
        v = version_de(ident, numero)
        message = corps.get("message")
        if not isinstance(message, str) or not message.strip() or len(message) > 4000:
            raise Refus(400, "message : un texte de 1 à 4000 caractères")
        conversation = str(corps.get("conversation") or "1")
        if not CONVERSATION.fullmatch(conversation):
            raise Refus(400, "conversation : lettres, chiffres, - et _")
        conf = Config.model_validate(v["config"])
        if regles.manques(conf):
            raise Refus(409, "version incomplète", regles.manques(conf))
        reponse = await essayer(conf, numero, message, conversation, cles, essais, principal=principal_essai)
        versions.noter_essai(ident, numero)
        return {"version": numero, "conversation": conversation, "reponse": reponse}

    @r.post("/clients/{ident}/versions/{numero}/activer")
    async def activer(ident: str, numero: int, qui: Identite = Depends(identite), corps: dict | None = Body(None)):
        c = client_de(qui, ident)
        v = version_de(ident, numero)
        forcer = bool((corps or {}).get("forcer"))
        if qui.role == "client":
            if (c.get("metadata") or {}).get("gere_par_megga"):
                raise Refus(403, "MEGGA a repris la main sur cet agent : la mise en service passe par MEGGA")
            if forcer:
                raise Refus(403, "forcer : réservé à MEGGA")
        if c.get("current_version") == numero:
            raise Refus(409, "cette version est déjà en service")
        if v["etat"] == "brouillon" and v["essais"] == 0 and not forcer:
            raise Refus(409, "essayez d'abord cette version (mode d'essai)")
        conf = Config.model_validate(v["config"])  # revalidée par le code en service
        if regles.manques(conf):
            raise Refus(409, "version incomplète", regles.manques(conf))
        if conf.zone in regles.ZONES_PORTE:
            if porte is None:
                raise Refus(503, "porte non réglée (PORTE_URL)")
            try:
                annuaire = await porte.activer(conf, numero)
            except PorteErreur as e:
                raise Refus(502, "la porte a refusé la mise en service", {"statut": e.statut, "texte": e.texte}) from e
        else:
            # Suisse et installation chez le client : poussée par le pilotage (lot 6).
            annuaire = {"zone": conf.zone, "porte": False}
        retour = v["etat"] == "publiee"
        versions.mettre_en_service(ident, numero)
        return {"client": ident, "version_en_service": numero, "retour": retour, "annuaire": annuaire}

    @r.post("/clients/{ident}/reprise")
    async def reprise(ident: str, qui: Identite = Depends(identite), corps: dict = Body(...)):
        megga(qui)
        client_de(qui, ident)
        meta = versions.regler(ident, gere_par_megga=bool(corps.get("gere_par_megga", True)))
        return {"client": ident, "gere_par_megga": meta["gere_par_megga"]}

    @r.post("/clients/{ident}/jetons", status_code=201)
    async def jeton(ident: str, qui: Identite = Depends(identite)):
        megga(qui)
        client_de(qui, ident)
        return {"client": ident, "jeton": jetons.creer(ident)}

    @r.delete("/clients/{ident}/jetons")
    async def revoquer(ident: str, qui: Identite = Depends(identite)):
        megga(qui)
        client_de(qui, ident)
        return {"client": ident, "retires": jetons.revoquer(ident)}

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
