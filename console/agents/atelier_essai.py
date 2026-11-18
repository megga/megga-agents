"""L'atelier d'essai local de l'admin MEGGA : le vrai atelier (`atelier.app.creer`) sur SQLite, devant une porte simulée.

La porte invente l'activité, les alertes, les conversations et les clés de quatre clients fictifs, sur les modèles
de FaussePorte (tests/test_lot5.py), PorteSuivie (tests/test_suivi.py) et PorteAuxCles (tests/test_lot6_api.py).
Le quatrième client tourne hors Cloudflare : son pilote inventé envoie des relevés signés par `noyau.pilotage.entetes`,
comme `releve_signe` (tests/test_lot6_pilote.py). Il ne sert qu'au développement et aux essais de bout en bout ;
aucun nom de vrai client n'y figure. Le moteur n'est pas modifié.

Environnement :
  ATELIER_JETON    obligatoire : le jeton de MEGGA (l'ADMIN_TOKEN de l'atelier), celui que la console présente
  ATELIER_DONNEES  facultatif : son dossier (par défaut console/.donnees/atelier-essai, base sqlite:///…/atelier.db)

Lancement, depuis console/ : `ATELIER_JETON=… ../.venv/bin/python -m uvicorn atelier_essai:app --app-dir agents --host 127.0.0.1 --port 8198`
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from atelier.app import creer
from atelier.porte import PorteErreur
from noyau import pilotage
from noyau.config import SANS_WHATSAPP_SCHEMA
from serveur import ModeleEssai

journal = logging.getLogger("megga.console.atelier-essai")

HOTE = "127.0.0.1"  # jamais ailleurs : uvicorn se lance avec --host 127.0.0.1
DOSSIER = Path(__file__).resolve().parent.parent / ".donnees" / "atelier-essai"
JOUR = 86400
RELEVE_CHAQUE = 60  # le pilote d'une installation relève chaque minute ; au-delà de 5 minutes, elle serait silencieuse

# Les quatre clients fictifs, créés par l'atelier lui-même d'après un modèle par métier, comme MEGGA le ferait.
CLIENTS = (
    {"gabarit": "generaliste", "nom_agent": "Lou",
     "client": {"id": "boulangerie-essai", "entreprise": "Boulangerie des Essais", "zone": "europe", "numero_id": "100000000000011"}},
    {"gabarit": "generaliste", "nom_agent": "Max",
     "client": {"id": "garage-essai", "entreprise": "Garage des Essais", "zone": "europe", "numero_id": "100000000000012"}},
    {"gabarit": "immobilier", "nom_agent": "Léa",
     "client": {"id": "agence-essai", "entreprise": "Agence des Essais", "zone": "europe", "numero_id": "100000000000013"}},
    {"gabarit": "generaliste", "nom_agent": "Noé", "client": {"id": "chalet-essai", "entreprise": "Chalet des Essais", "zone": "client"}},
)
CHALET = "chalet-essai"
# Un seul modèle a son tarif : le secours (deepseek-v4-pro), la voix et l'écoute sortent « sans tarif ».
TARIFS = {"devise": "USD", "modeles": {"claude-sonnet-5-5": {"entree": 3, "sortie": 15, "cache_lecture": 0.3, "cache_ecriture": 3.75}}}

# Ce que fait chaque agent en un jour ; le suivi d'une période en est le multiple. personnes et rappels : sur toute période.
PAR_JOUR = {
    "boulangerie-essai": {"tours": 14, "tours_api": 2, "secours": 0, "personnes": 2, "rappels": 1, "voix": 1800, "entendus": 2, "dits": 1},
    "garage-essai": {"tours": 9, "tours_api": 0, "secours": 1, "personnes": 4, "rappels": 0, "voix": 0, "entendus": 1, "dits": 0},
    "agence-essai": {"tours": 6, "tours_api": 0, "secours": 0, "personnes": 3, "rappels": 2, "voix": 0, "entendus": 0, "dits": 0},
    "chalet-essai": {"tours": 4, "tours_api": 1, "secours": 0, "personnes": 2, "rappels": 0, "voix": 0, "entendus": 0, "dits": 0},
}

# Le journal du noyau : (genre, il y a combien d'heures, détail). Seul le garage a des échecs.
ECHECS = {
    "garage-essai": (("tour_echec", 2, "RuntimeError"), ("envoi_refuse", 5, "131047"), ("tour_echec", 30, "TimeoutError"),
                     ("tour_echec", 220, "RuntimeError")),
}

# Les pannes du conteneur, gardées par la porte : (quoi, il y a combien de minutes, message, résolue il y a combien de minutes).
PANNES = {
    "garage-essai": (("demarrage", 180, "secret manquant", 150), ("transmission", 40, "conteneur arrêté", None)),
}

# Les conversations : (il y a combien de minutes, sens, texte). Des numéros fictifs.
CONVERSATIONS = {
    "boulangerie-essai": {
        "+41790000001": ((190, "recu", "Bonjour, vous avez encore des tresses au beurre pour samedi ?"),
                         (190, "envoye", "Bonjour ! Oui, je vous en mets une de côté. À quel nom ?"),
                         (185, "recu", "Au nom de Martin, merci."),
                         (185, "envoye", "C'est noté : une tresse au beurre pour samedi, au nom de Martin.")),
        "+41790000002": ((45, "recu", "Vous êtes ouverts le lundi ?"),
                         (45, "envoye", "Nous sommes fermés le lundi, ouverts du mardi au dimanche dès 7 h.")),
    },
    "garage-essai": {
        "+41790000003": ((130, "recu", "Ma voiture fait un bruit au freinage."),
                         (130, "envoye", "Je transmets à l'atelier. Quand pourriez-vous passer ?")),
    },
    "agence-essai": {
        "+41790000004": ((600, "recu", "Je cherche un trois pièces à louer, près de la gare."),
                         (600, "envoye", "Volontiers. Quel est votre budget, et pour quand ?")),
    },
}


class Disque:
    """Ce que la porte (son annuaire, les clés de ses conteneurs) et l'installation (son pilote) gardent d'une relance
    à l'autre, comme l'annuaire D1 de la vraie porte : un fichier JSON, écrit à côté puis remplacé."""

    def __init__(self, fichier: Path):
        self.fichier = fichier
        try:
            self.donnees: dict = json.loads(fichier.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            self.donnees = {}

    def section(self, nom: str) -> dict:
        return self.donnees.setdefault(nom, {})

    def garder(self) -> None:
        provisoire = self.fichier.with_suffix(".tmp")
        provisoire.write_text(json.dumps(self.donnees, ensure_ascii=False, indent=1))
        os.replace(provisoire, self.fichier)


def jetons(fournisseur: str, tours: int) -> dict:
    return {"fournisseur": fournisseur, "tours": tours, "entree": 2600 * tours, "sortie": 380 * tours,
            "cache_lecture": 9200 * tours, "cache_ecriture": 700 * tours}


def echecs(ident: str, maintenant: float) -> list[dict]:
    return [{"quand": maintenant - h * 3600, "genre": g, "detail": d} for g, h, d in ECHECS.get(ident, ())]


def activite(ident: str, depuis: float, maintenant: float) -> dict:
    """L'activité d'une période, de la forme de noyau/suivi.py (resumer)."""
    jours = max(1, round((maintenant - depuis) / JOUR))
    j = PAR_JOUR[ident]
    tours, secours = j["tours"] * jours, j["secours"] * jours
    modeles = {"claude-sonnet-5-5": jetons("anthropic", tours - secours)}
    if secours:
        modeles["deepseek-v4-pro"] = jetons("deepseek", secours)
    notes: dict[str, dict] = {}
    for a in echecs(ident, maintenant):
        if a["quand"] >= depuis:
            n = notes.setdefault(a["genre"], {"nombre": 0, "quantite": 0.0})
            n["nombre"] += 1
            n["quantite"] += 1
    if j["voix"]:
        notes["voix_caracteres"] = {"nombre": j["dits"] * jours, "quantite": float(j["voix"] * jours)}
    for genre, n in (("vocal_entendu", j["entendus"]), ("vocal_dit", j["dits"])):
        if n:
            notes[genre] = {"nombre": n * jours, "quantite": float(n * jours)}
    return {"depuis": depuis, "tours": tours, "tours_en_echec": notes.get("tour_echec", {}).get("nombre", 0), "secours": secours,
            "personnes": j["personnes"], "tours_api": j["tours_api"] * jours, "derniere_activite": maintenant - 600,
            "modeles": modeles, "journal": notes, "rappels_en_attente": j["rappels"]}


def conteneur(ident: str, maintenant: float) -> dict:
    """L'état du conteneur dans l'annuaire : ses pannes (en millisecondes, comme la porte) ; arrêté si l'une dure."""
    ms = maintenant * 1000
    pannes = [{"quand": ms - m * 60_000, "quoi": q, "message": t, "resolue": None if r is None else ms - r * 60_000}
              for q, m, t, r in PANNES.get(ident, ())]
    return {"demarre": all(p["resolue"] for p in pannes), "alertes": pannes}


def fils(ident: str, maintenant: float) -> dict[str, list[dict]]:
    return {p: [{"quand": maintenant - m * 60, "sens": s, "genre": "texte", "texte": t} for m, s, t in messages]
            for p, messages in CONVERSATIONS.get(ident, {}).items()}


class PorteEssai:
    """La porte simulée : l'annuaire et ses mises en service (FaussePorte), le suivi des conteneurs (PorteSuivie),
    les clés des logiciels gardées en empreinte (PorteAuxCles)."""

    def __init__(self, disque: Disque):
        self.disque = disque
        self.annuaire: dict[str, int] = disque.section("annuaire")
        self.gardees: dict[str, list] = disque.section("cles")

    async def activer(self, conf, version):
        self.annuaire[conf.id] = version
        self.disque.garder()
        return {"ok": True, "redemarre": True}

    async def etats(self, ident=None):
        maintenant = time.time()
        return {c: {"id": c, "actif": 1, "version": v, "conteneur": conteneur(c, maintenant)}
                for c, v in self.annuaire.items() if ident in (None, c)}

    async def suivi(self, ident, chemin="", **params):
        maintenant = time.time()
        limite = params.get("limite") or 50
        if chemin == "":
            return activite(ident, float(params.get("depuis") or 0), maintenant)
        if chemin == "/alertes":
            return {"alertes": [a for a in echecs(ident, maintenant) if a["quand"] >= float(params.get("depuis") or 0)]}
        if chemin == "/conversations":
            personnes = [{"personne": p, "messages": len(m), "derniere": m[-1]["quand"]} for p, m in fils(ident, maintenant).items()]
            return {"conversations": sorted(personnes, key=lambda p: p["derniere"], reverse=True)[:limite]}
        if chemin.startswith("/conversations/"):
            personne = chemin.removeprefix("/conversations/")
            return {"personne": personne, "messages": fils(ident, maintenant).get(personne, [])[-limite:]}
        raise PorteErreur(404, "introuvable")

    async def cles(self, ident, methode="GET", chemin="", corps=None):
        liste = self.gardees.setdefault(ident, [])
        if methode == "POST":
            liste.append({"id": corps["id"], "logiciel": corps["logiciel"], "par_minute": corps["par_minute"], "cree": time.time(),
                          "retiree": None})
            self.disque.garder()
            return {"id": corps["id"], "logiciel": corps["logiciel"], "par_minute": corps["par_minute"]}
        if methode == "DELETE":
            for c in liste:
                if c["id"] == chemin[1:] and c["retiree"] is None:
                    c["retiree"] = time.time()
            self.disque.garder()
            return {"id": chemin[1:], "retiree": True}
        return {"cles": [dict(c) for c in liste]}


class PiloteEssai:
    """Le pilote inventé de l'installation de chalet-essai : un relevé signé, comme releve_signe (tests/test_lot6_pilote.py).
    Il applique d'office chaque ordre remis (simulé : le vrai pilote vérifie la signature, pilote/service.py) et le dit
    au relevé suivant. Sa clé est tirée au démarrage, jamais écrite ; ce qu'il sert est gardé sur le disque."""

    def __init__(self, cle, disque: Disque):
        self.cle = cle
        self.disque = disque
        self.etat: dict = disque.section("pilote")  # dernier ordre reçu, version de configuration, version d'image
        self.statuts: list[dict] = []
        self.quand = 0.0
        self.branche = False  # sa clé est enregistrée dans l'atelier

    def requete(self) -> tuple[bytes, dict]:
        maintenant = time.time()
        agent = {"ok": True, "version": self.etat.get("image", "0.2.0"), "revision": "essai", "schema": SANS_WHATSAPP_SCHEMA,
                 "licence": {"etat": "valide", "jusqu_au": "2027-12-31"}}
        if self.etat.get("version"):
            agent["configuration"] = {"source": "pilotage", "version": self.etat["version"]}
        fenetres = {str(j): activite(CHALET, maintenant - j * JOUR, maintenant) for j in (1, 7, 30)}
        corps = {"pilotage": "complet", "accord": True, "dernier_ordre": self.etat.get("dernier", 0), "ordres": self.statuts[-20:],
                 "etat": {"agent": agent, "mises_a_jour": False}, "suivi": {"calcule": maintenant, "fenetres": fenetres, "alertes": []}}
        brut = json.dumps(corps).encode()
        return brut, {**pilotage.entetes(CHALET, self.cle, "POST", "/pilotage/releve", brut), "content-type": "application/json"}

    def lire(self, statut: int, reponse: dict) -> bool:
        """La réponse d'un relevé ; vrai s'il a reçu des ordres (le relevé suivant dira qu'ils sont appliqués)."""
        if statut != 200:
            journal.warning("relevé de %s refusé (%s)", CHALET, statut)
            self.branche = statut != 401  # une clé révoquée ou remplacée : il se tait
            return False
        self.quand = time.time()
        recus = [pilotage.contenu(j) for j in reponse.get("ordres", [])]
        for o in recus:
            contenu = o.get("contenu") or {}
            if o.get("genre") == "config":
                self.etat["version"] = contenu.get("version")
            elif o.get("genre") == "image":
                self.etat["image"] = contenu.get("version")
            self.etat["dernier"] = max(self.etat.get("dernier", 0), int(o.get("numero") or 0))
            self.statuts.append({"numero": o.get("numero"), "etat": "applique", "detail": ""})
        if recus:
            self.disque.garder()
        return bool(recus)

    def relever(self, t: TestClient) -> None:
        """Au démarrage : un relevé, et un second s'il a reçu des ordres."""
        for _ in range(2):
            brut, entetes = self.requete()
            r = t.post("/pilotage/releve", content=brut, headers=entetes)
            if not self.lire(r.status_code, r.json()):
                return

    async def relever_au_fil(self, app: FastAPI) -> None:
        """En marche : le même relevé, par l'app elle-même (sans réseau)."""
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://atelier-essai") as c:
            for _ in range(2):
                brut, entetes = self.requete()
                r = await c.post("/pilotage/releve", content=brut, headers=entetes)
                if not self.lire(r.status_code, r.json()):
                    return


def cle_jetable():
    """Une clé Ed25519 et sa forme sur une ligne, comme cle_jetable (tests/test_lot5.py) : tirée au démarrage, jamais écrite."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

    cle = Ed25519PrivateKey.generate()
    return cle, base64.b64encode(cle.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())).decode()


def attendu(r) -> dict:
    if r.status_code >= 300:
        raise RuntimeError(f"atelier d'essai : {r.request.method} {r.request.url.path} {r.status_code} {r.text[:200]}")
    return r.json()


def peupler(t: TestClient, porte: PorteEssai) -> None:
    """Les tarifs et les quatre clients, créés et mis en service par l'atelier lui-même."""
    attendu(t.put("/atelier/tarifs", json=TARIFS))
    for c in CLIENTS:
        attendu(t.post("/atelier/clients", json=c))
        attendu(t.post(f"/atelier/clients/{c['client']['id']}/versions/1/activer", json={"forcer": True}))
    attendu(t.post("/atelier/clients/agence-essai/versions", json={"changements": {"ton": "chaleureux et précis, vouvoie en français"}}))
    attendu(t.post("/atelier/clients/agence-essai/versions/2/activer", json={"forcer": True}))
    # Une mise en service interrompue après la porte : l'annuaire sert encore la version 1, d'où l'écart.
    porte.annuaire["agence-essai"] = 1
    porte.disque.garder()
    attendu(t.post("/atelier/clients/boulangerie-essai/cles", json={"logiciel": "caisse", "par_minute": 30}))  # montrée une fois, oubliée


def brancher(t: TestClient, pilote: PiloteEssai) -> None:
    """La clé du pilote, tirée à ce démarrage, enregistrée pour l'installation (sauf révoquée), puis un premier relevé."""
    installations = {i["client"]: i for i in attendu(t.get("/atelier/installations"))["installations"]}
    if CHALET in installations and installations[CHALET]["revoquee"] is not None:
        return
    attendu(t.put(f"/atelier/clients/{CHALET}/installation", json={"cle_publique": pilotage.en_texte(pilote.cle.public_key())}))
    pilote.branche = True
    pilote.relever(t)


def creer_app() -> FastAPI:
    jeton = os.environ.get("ATELIER_JETON", "")
    if not jeton:
        raise RuntimeError("ATELIER_JETON manquant : le jeton de MEGGA que la console présente")
    dossier = Path(os.environ.get("ATELIER_DONNEES") or DOSSIER)
    dossier.mkdir(parents=True, exist_ok=True)
    _, cle_pilotage = cle_jetable()
    cle_installation, _ = cle_jetable()
    disque = Disque(dossier / "simulation.json")
    porte, pilote = PorteEssai(disque), PiloteEssai(cle_installation, disque)
    app = creer({"ADMIN_TOKEN": jeton, "DATABASE_URL": f"sqlite:///{dossier}/atelier.db", "ESSAIS_DIR": str(dossier / "essais"),
                 "PILOTAGE_CLE": cle_pilotage}, porte=porte, principal_essai=ModeleEssai())
    app.state.pilote = pilote

    @app.middleware("http")
    async def pilote_au_fil_des_lectures(requete: Request, suite):
        """L'installation reste vivante tant qu'on lit l'atelier : un relevé par minute au plus."""
        if pilote.branche and requete.url.path.startswith("/atelier") and time.time() - pilote.quand > RELEVE_CHAQUE:
            pilote.quand = time.time()
            await pilote.relever_au_fil(app)
        return await suite(requete)

    t = TestClient(app, headers={"authorization": f"Bearer {jeton}"})
    if not attendu(t.get("/atelier/clients"))["clients"]:
        peupler(t, porte)
    brancher(t, pilote)
    return app


app = creer_app()
