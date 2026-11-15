"""Le pilotage des installations hors Cloudflare, vu de MEGGA (le protocole : noyau/pilotage.py).

Une installation chez le client (puis en zone suisse) n'ouvre aucun port : son pilote appelle la
porte, qui transmet ici (POST /pilotage/releve) ; l'atelier vérifie la signature de l'installation,
garde son dernier relevé, et lui remet les ordres signés qui l'attendent.

  enregistrer   la clé publique de l'installation, à sa mise en service (MEGGA)
  revoquer      plus aucun relevé n'est accepté de cette clé
  deposer       un ordre signé : une version de configuration (mise en service), ou une image proposée
  releve        un relevé du pilote : son état, son suivi, ce que sont devenus les ordres ; rend ceux à remettre

Tout est inscrit au journal du pilotage (megga_pilotage), comme chez le client.
"""

from __future__ import annotations

import json
import time

from noyau import pilotage, stockage

SILENCE = 300  # sans relevé depuis 5 minutes, une installation est signalée silencieuse
TAILLE = 256 * 1024  # un relevé : l'état, le suivi de 3 périodes, au plus 100 alertes


def version_de(jeton: str) -> dict:
    """La version d'un ordre (son contenu, sans la configuration), pour l'afficher."""
    o = pilotage.contenu(jeton)
    c = o.get("contenu") if isinstance(o.get("contenu"), dict) else {}
    return {k: c[k] for k in ("version", "image") if k in c}


class Pilotage:
    def __init__(self, url: str, cle=None, horloge=time.time):
        """`cle` : la clé privée de pilotage de MEGGA (PILOTAGE_CLE) ; sans elle, aucun ordre n'est signé."""
        self.installations = stockage.Installations(url)
        self.ordres = stockage.Ordres(url)
        self.journal = stockage.JournalPilotage(url)
        self.nonces = stockage.Nonces(url)
        self.cle = cle
        self.horloge = horloge

    # Les clés des installations

    def enregistrer(self, client: str, texte: str) -> str:
        """La clé publique remise par l'installation (python -m pilote cle) ; rend son empreinte."""
        ligne = pilotage.en_texte(pilotage.cle_publique(texte))
        self.installations.enregistrer(client, ligne, self.horloge())
        self.journal.noter(client, "cle_enregistree", None, f"clé {pilotage.empreinte(ligne)}")
        return pilotage.empreinte(ligne)

    def revoquer(self, client: str) -> bool:
        if not self.installations.revoquer(client, self.horloge()):
            return False
        self.journal.noter(client, "cle_revoquee", None, "plus aucun relevé accepté de cette installation")
        return True

    def _cle_de(self, client: str):
        ligne = self.installations.cle(client)
        return pilotage.cle_publique(ligne) if ligne else None

    # Les ordres

    def deposer(self, client: str, genre: str, contenu: dict, auteur: str) -> dict:
        """Un ordre signé pour l'installation de ce client ; il part à son prochain relevé."""
        if self.cle is None:
            raise pilotage.PilotageRefuse("clé de pilotage absente : l'atelier ne peut pas signer d'ordre (scripts/pilotage.py poser)")
        o = self.ordres.deposer(client, genre, lambda n, q: pilotage.ordre(client, n, genre, contenu, self.cle, q),
                                pilotage.DUREE_ORDRE, self.horloge())
        for n in o["remplaces"]:
            self.journal.noter(client, "remplace", n, f"remplacé par l'ordre {o['numero']} avant d'être remis")
        quoi = f"configuration, version {contenu.get('version')}" if genre == "config" else f"image {contenu.get('version')} proposée"
        self.journal.noter(client, "depose", o["numero"], f"{quoi}, par {auteur}")
        return o

    def en_cours(self, client: str, version: int) -> int | None:
        """Le numéro d'un ordre pour cette version de configuration qui n'a pas encore abouti, s'il y en a un."""
        for l in self.ordres.lister(client, 50, etats=("en_attente", "remis", "attente_accord", "a_appliquer")):
            if l["genre"] == "config" and version_de(l["jeton"]).get("version") == version:
                return l["numero"]
        return None

    # Le relevé d'une installation

    def releve(self, methode: str, chemin: str, entetes, corps: bytes) -> dict:
        """Un relevé signé : l'état et le suivi gardés, les états des ordres notés ; rend les ordres à remettre."""
        maintenant = self.horloge()
        if len(corps) > TAILLE:
            raise pilotage.PilotageRefuse("relevé trop gros")
        client, nonce = pilotage.verifier_requete(entetes, methode, chemin, corps, self._cle_de, maintenant)
        if not self.nonces.nouveau(client, nonce, maintenant):
            raise pilotage.PilotageRefuse("requête rejouée")
        try:
            d = json.loads(corps)
        except ValueError:
            raise pilotage.PilotageRefuse("relevé illisible") from None
        if not isinstance(d, dict) or d.get("pilotage") not in ("suivi", "complet"):
            raise pilotage.PilotageRefuse("relevé : pilotage « suivi » ou « complet »")
        etat = d.get("etat") if isinstance(d.get("etat"), dict) else {}
        etat = {**etat, "pilotage": d["pilotage"], "accord": d.get("accord") is True}
        suivi = d.get("suivi") if isinstance(d.get("suivi"), dict) else None
        self.installations.noter_releve(client, etat, suivi, maintenant)
        for ch in self.ordres.noter_etats(client, d.get("ordres") if isinstance(d.get("ordres"), list) else [], maintenant):
            self.journal.noter(client, ch["etat"], ch["numero"], ch["detail"] or "selon l'installation")
        remis: list[str] = []
        dernier = d.get("dernier_ordre")
        # Sous « suivi », rien n'est remis : c'est le réglage du client qui décide.
        if d["pilotage"] == "complet" and isinstance(dernier, int) and not isinstance(dernier, bool):
            lignes, nouveaux, expires = self.ordres.a_remettre(client, dernier, maintenant)
            for n in expires:
                self.journal.noter(client, "expire", n, "pas reçu par l'installation dans la semaine")
            for n in nouveaux:
                self.journal.noter(client, "remis", n, "remis à l'installation")
            remis = [l["jeton"] for l in lignes]
        return {"heure": maintenant, "ordres": remis}

    # Ce que l'atelier montre

    def bref(self, inst: dict, courante: int | None = None) -> dict:
        """L'état d'une installation d'après son dernier relevé, sans son suivi."""
        maintenant = self.horloge()
        etat = inst.get("etat") or {}
        agent = etat.get("agent") if isinstance(etat.get("agent"), dict) else {}
        config = agent.get("configuration") if isinstance(agent.get("configuration"), dict) else None
        version = config.get("version") if config and config.get("source") == "pilotage" else None
        releve = inst.get("releve")
        return {
            "cle": pilotage.empreinte(inst["cle"]),
            "enregistree": inst["enregistree"],
            "revoquee": inst["revoquee"],
            "releve": releve,
            "silencieuse": inst["revoquee"] is None and (releve is None or maintenant - releve > SILENCE),
            "pilotage": etat.get("pilotage"),
            "accord": etat.get("accord"),
            "agent": {k: agent[k] for k in ("ok", "erreur", "version", "revision", "schema", "licence") if k in agent},
            "configuration": config,
            # La version servie par l'installation n'est pas celle en service dans l'atelier (inconnue sans relevé).
            "ecart": None if releve is None or courante is None else version != courante,
        }

    def vue(self, client: str, courante: int | None) -> dict:
        """L'installation d'un client : son état, ses derniers ordres et le journal du pilotage."""
        inst = self.installations.lire(client)
        ordres = [{"numero": l["numero"], "genre": l["genre"], **version_de(l["jeton"]), "etat": l["etat"],
                   "detail": l["detail"], "cree": l["cree"], "expire": l["expire"], "maj": l["maj"]}
                  for l in self.ordres.lister(client, 20)]
        return {"installation": self.bref(inst, courante) if inst else None, "ordres": ordres,
                "journal": self.journal.lire(client, 50)}

    def toutes(self, courantes: dict[str, int | None]) -> list[dict]:
        return [{"client": i["client"], **self.bref(i, courantes.get(i["client"]))} for i in self.installations.toutes()]

    def suivi(self, client: str, jours: int) -> tuple[dict, dict]:
        """L'activité d'une période (1, 7 ou 30 jours) d'après le dernier suivi de l'installation, et l'installation."""
        inst = self.installations.lire(client)
        if inst is None or inst["revoquee"] is not None:
            raise pilotage.PilotageRefuse("aucune installation enregistrée pour ce client")
        s = inst.get("suivi") or {}
        fenetres = s.get("fenetres") if isinstance(s.get("fenetres"), dict) else None
        if not fenetres:
            raise pilotage.PilotageRefuse("pas encore de suivi : l'installation l'envoie toutes les 5 minutes (PILOTAGE=suivi ou complet)")
        activite = fenetres.get(str(jours))
        if not isinstance(activite, dict):
            raise pilotage.PilotageRefuse("jours : 1, 7 ou 30 pour une installation chez le client")
        return {**activite, "calcule": s.get("calcule")}, inst

    def alertes(self, client: str, depuis: float, courante: int | None) -> list[dict]:
        """Ce qui ne va pas : installation absente, révoquée ou silencieuse, agent injoignable, licence, écart,
        ordres refusés ou en échec, et les échecs relevés dans l'installation."""
        maintenant = self.horloge()
        inst = self.installations.lire(client)
        if inst is None:
            return [{"quand": maintenant, "genre": "installation_absente", "detail": "aucune clé d'installation enregistrée"}]
        liste = []
        b = self.bref(inst, courante)
        if inst["revoquee"] is not None:
            liste.append({"quand": inst["revoquee"], "genre": "installation_revoquee", "detail": ""})
        elif b["silencieuse"]:
            depuis_quand = "jamais" if b["releve"] is None else time.strftime("%d.%m.%Y %H:%M", time.gmtime(b["releve"])) + " UTC"
            liste.append({"quand": maintenant, "genre": "installation_silencieuse", "detail": f"dernier relevé : {depuis_quand}"})
        if b["releve"] is not None and b["agent"] and not b["agent"].get("ok"):
            liste.append({"quand": b["releve"], "genre": "agent_en_panne", "detail": b["agent"].get("erreur") or "/sante en échec"})
        licence = b["agent"].get("licence") if isinstance(b["agent"].get("licence"), dict) else {}
        if licence.get("etat") in ("expiree", "hors_delai"):
            liste.append({"quand": b["releve"], "genre": f"licence_{licence['etat']}", "detail": f"jusqu'au {licence.get('jusqu_au')}"})
        if b["ecart"]:
            servie = b["configuration"] or {}
            liste.append({"quand": b["releve"], "genre": "ecart", "detail": "l'installation sert " + (
                f"la version {servie.get('version')}" if servie.get("source") == "pilotage" else "son fichier") + f", l'atelier la {courante}"})
        for l in self.ordres.lister(client, 50, etats=("refuse", "echec", "expire")):
            if l["maj"] >= depuis:
                liste.append({"quand": l["maj"], "genre": f"ordre_{l['etat']}", "detail": f"ordre {l['numero']} : {l['detail']}"})
        for a in ((inst.get("suivi") or {}).get("alertes") or []):
            if isinstance(a, dict) and isinstance(a.get("quand"), (int, float)) and a["quand"] >= depuis:
                liste.append({"quand": a["quand"], "genre": str(a.get("genre")), "detail": str(a.get("detail") or "")})
        return liste
