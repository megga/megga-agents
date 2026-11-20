"""Les alertes envoyées de la console de MEGGA (20.11.2026).

Une alerte se règle en trois temps, comme chez Langfuse : la mesure, les seuils, l'envoi. Toutes les 5 minutes, la
porte demande à l'atelier d'évaluer chaque règle sur chaque client actif, d'après le relevé chiffré (atelier/releves.py) :
aucun conteneur n'est réveillé, aucune conversation n'est lue. Un message part au changement d'état (alerte,
avertissement, sans données, rétabli), puis en rappel à l'intervalle choisi, jamais quand la règle est en pause.

Écrit pour la plateforme, d'après le principe des moniteurs de Langfuse (deux seuils, absence de données, rappel),
sans reprendre leur code.
"""

from __future__ import annotations

import json
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Column, Float, String, delete, insert, select, update

from noyau.stockage import _table

ID = r"^[a-z0-9][a-z0-9-]{1,39}$"
FENETRE_MAX = 7  # jours : la période relue à chaque évaluation
REGLES_MAX = 20

# La mesure : son libellé, son unité, et comment la lire dans le relevé d'un client (atelier/releves.py, rassembler).
MESURES: dict[str, tuple[str, str]] = {
    "silencieux": ("Agent silencieux, sans relevé depuis 40 minutes", "oui ou non"),
    "pannes_en_cours": ("Pannes du conteneur en cours", "nombre"),
    "ecart": ("La porte ne sert pas la version en service", "oui ou non"),
    "taux_echec": ("Tours en échec", "%"),
    "secours": ("Recours au modèle de secours", "nombre"),
    "tours": ("Tours", "nombre"),
    "cout": ("Coût des modèles et de la voix", "devise"),
    "reponses_lentes": ("Réponses lentes", "nombre"),
    "plafond": ("Plafond du jour atteint", "nombre"),
    "envois_en_echec": ("Envois refusés ou en échec", "nombre"),
    # Les signaux de sécurité, comptés par la garde du noyau (noyau/tour.py).
    "secrets_masques": ("Secrets masqués dans une réponse", "nombre"),
    "debit_depasse": ("Messages arrêtés pour débit excessif", "nombre"),
}
JOURNAL = {"plafond": ("plafond",), "envois_en_echec": ("envoi_refuse", "envoi_echec"),
           "secrets_masques": ("secret_masque",), "debit_depasse": ("debit_depasse",)}
ETATS = ("ok", "avertissement", "alerte", "sans_donnees")


class Regle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=ID)
    nom: str = Field(min_length=1, max_length=80)
    mesure: Literal[tuple(MESURES)]  # type: ignore[valid-type]
    comparaison: Literal[">", ">=", "<", "<="] = ">="
    alerte: float
    avertissement: float | None = None
    fenetre_jours: int = Field(1, ge=1, le=FENETRE_MAX)  # 1 : le jour en cours (UTC)
    # Sans données (agent sans tour, sans relevé) : compter bon, garder l'état d'avant, ou le signaler.
    sans_donnees: Literal["ok", "garder", "signaler"] = "ok"
    clients: list[str] = Field(default_factory=list, max_length=200)  # vide : tous les clients
    destinations: list[str] = Field(default_factory=list, max_length=10)
    rappel_heures: int = Field(0, ge=0, le=168)  # 0 : pas de rappel
    en_pause: bool = False

    @model_validator(mode="after")
    def _seuils(self):
        a, v = self.alerte, self.avertissement
        if v is not None and (v >= a if self.comparaison[0] == ">" else v <= a):
            raise ValueError("l'avertissement se franchit avant l'alerte")
        return self


# Proposées tant qu'aucune règle n'est enregistrée ; sans destination, rien ne part.
PROPOSEES = [
    {"id": "silencieux", "nom": "Agent silencieux", "mesure": "silencieux", "alerte": 1, "rappel_heures": 4},
    {"id": "pannes", "nom": "Panne du conteneur", "mesure": "pannes_en_cours", "alerte": 1, "rappel_heures": 4},
    {"id": "echecs", "nom": "Tours en échec", "mesure": "taux_echec", "comparaison": ">", "alerte": 10, "avertissement": 5},
    {"id": "ecart", "nom": "Version non servie", "mesure": "ecart", "alerte": 1},
    {"id": "plafond", "nom": "Plafond du jour atteint", "mesure": "plafond", "alerte": 1, "avertissement": None},
    {"id": "secrets", "nom": "Secret masqué", "mesure": "secrets_masques", "alerte": 1},
]


def regles_de(brut) -> list[Regle]:
    """Les règles enregistrées, ou les proposées tant qu'il n'y en a pas."""
    return [Regle.model_validate(r) for r in (PROPOSEES if brut is None else brut)]


def valider_regles(brut) -> list[Regle]:
    if not isinstance(brut, list) or len(brut) > REGLES_MAX:
        raise ValueError(f"une liste de {REGLES_MAX} règles au plus")
    regles = [Regle.model_validate(r) for r in brut]
    if len({r.id for r in regles}) != len(regles):
        raise ValueError("deux règles portent le même identifiant")
    return regles


def jours_de_fenetre(client: dict, fenetre: int, maintenant: float) -> list[dict]:
    debut = time.strftime("%Y-%m-%d", time.gmtime(maintenant - (fenetre - 1) * 86400))
    return [j for d, j in (client.get("jours") or {}).items() if d >= debut]


def mesurer(client: dict, mesure: str, fenetre: int, maintenant: float) -> float | None:
    """La valeur d'une mesure pour un client rassemblé, sur ses `fenetre` derniers jours ; None : sans données."""
    if mesure == "silencieux":
        return float(bool(client.get("silencieux")))
    if mesure == "ecart":
        return float(bool(client.get("ecart")))
    if not client.get("releve_le"):
        return None  # aucun relevé : seul le silence se juge
    if mesure == "pannes_en_cours":
        return float(len(((client.get("etat") or {}).get("pannes_en_cours")) or []))
    jours = jours_de_fenetre(client, fenetre, maintenant)
    somme = lambda f: float(sum(f(j) for j in jours))  # noqa: E731
    if mesure == "taux_echec":
        tours = somme(lambda j: j.get("tours") or 0)
        return round(100 * somme(lambda j: j.get("tours_en_echec") or 0) / tours, 1) if tours else None
    if mesure in ("secours", "tours"):
        return somme(lambda j: j.get(mesure) or 0)
    if mesure == "cout":
        return round(somme(lambda j: j.get("cout") or 0), 4)
    if mesure == "reponses_lentes":
        return somme(lambda j: (j.get("delais") or {}).get("lentes") or 0)
    genres = JOURNAL[mesure]
    return somme(lambda j: sum(((j.get("journal") or {}).get(g) or {}).get("nombre") or 0 for g in genres))


def franchi(valeur: float, comparaison: str, seuil: float) -> bool:
    return {">": valeur > seuil, ">=": valeur >= seuil, "<": valeur < seuil, "<=": valeur <= seuil}[comparaison]


def gravite(r: Regle, valeur: float | None) -> str:
    if valeur is None:
        return "sans_donnees"
    if franchi(valeur, r.comparaison, r.alerte):
        return "alerte"
    if r.avertissement is not None and franchi(valeur, r.comparaison, r.avertissement):
        return "avertissement"
    return "ok"


def decider(r: Regle, avant: dict | None, brute: str, maintenant: float) -> tuple[str, str | None]:
    """Le nouvel état et ce qu'il faut envoyer : « nouveau », « rappel », « retabli » ou rien."""
    precedent = (avant or {}).get("etat") or "ok"
    etat = brute
    if brute == "sans_donnees" and r.sans_donnees != "signaler":
        etat = "ok" if r.sans_donnees == "ok" else precedent
    if r.en_pause:
        return etat, None
    if etat != precedent:
        return etat, "retabli" if etat == "ok" else "nouveau"
    # Le rappel compte depuis le dernier envoi, ou depuis le changement d'état si aucun n'est parti (destinations en panne).
    envoye = (avant or {}).get("envoye_le") or (avant or {}).get("depuis")
    if etat != "ok" and r.rappel_heures and envoye and maintenant - envoye >= r.rappel_heures * 3600:
        return etat, "rappel"
    return etat, None


def nombre(v: float | None, unite: str) -> str:
    if v is None:
        return "sans données"
    if unite == "oui ou non":
        return "oui" if v else "non"
    texte = f"{v:.2f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))
    return texte.replace(".", ",") + (" %" if unite == "%" else "")


def message(r: Regle, genre: str, etat: str, client: dict, valeur: float | None, devise: str) -> dict:
    """Le message d'un envoi : des chiffres et le nom de l'entreprise, jamais une conversation."""
    libelle, unite = MESURES[r.mesure]
    unite_lue = devise if unite == "devise" else unite
    qui = " ".join(str(client.get("entreprise") or client.get("id")).split())[:80]  # une ligne : le sujet d'un courriel
    titre = {"alerte": "Alerte", "avertissement": "Avertissement", "sans_donnees": "Sans données", "ok": "Rétabli"}[etat]
    if genre == "rappel":
        titre = f"Rappel, {titre.lower()}"
    seuil = r.alerte if etat == "alerte" else r.avertissement
    detail = f"{libelle} : {nombre(valeur, unite_lue)}"
    if etat in ("alerte", "avertissement") and seuil is not None and unite != "oui ou non":
        detail += f", seuil {r.comparaison} {nombre(seuil, unite_lue)}"
    if unite == "devise" and valeur is not None:
        detail += f" {devise}"
    fenetre = "le jour en cours" if r.fenetre_jours == 1 else f"les {r.fenetre_jours} derniers jours"
    return {
        "sujet": f"{titre} : {r.nom}, {qui}",
        "texte": f"{titre} : {r.nom}, {qui}.\n{detail}, sur {fenetre}.",
        "donnees": {"regle": r.id, "nom": r.nom, "client": client.get("id"), "entreprise": client.get("entreprise"),
                    "mesure": r.mesure, "valeur": valeur, "comparaison": r.comparaison, "alerte": r.alerte,
                    "avertissement": r.avertissement, "fenetre_jours": r.fenetre_jours, "etat": etat, "envoi": genre},
    }


class Etats:
    """L'état de chaque règle pour chaque client (table megga_alertes_etats)."""

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_alertes_etats",
            Column("regle", String(40), primary_key=True),
            Column("client", String(63), primary_key=True),
            Column("etat", String(20), nullable=False),
            Column("depuis", Float, nullable=False),
            Column("valeur", Float, nullable=True),
            Column("envoye_le", Float, nullable=True),
            # Un envoi à reprendre : {"genre", "destinations"} restées en échec.
            Column("en_attente", String(2000), nullable=True),
        )

    def tous(self) -> dict[tuple[str, str], dict]:
        with self._e.connect() as c:
            lignes = c.execute(select(self._t)).mappings().all()
        return {(l["regle"], l["client"]): {**l, "en_attente": json.loads(l["en_attente"]) if l["en_attente"] else None}
                for l in lignes}

    def ecrire(self, regle: str, client: str, valeurs: dict, existe: bool) -> None:
        v = {**valeurs, "en_attente": json.dumps(valeurs["en_attente"]) if valeurs.get("en_attente") else None}
        t = self._t
        with self._e.begin() as c:
            if existe:
                c.execute(update(t).where(t.c.regle == regle, t.c.client == client).values(**v))
            else:
                c.execute(insert(t).values(regle=regle, client=client, **v))

    def retirer(self, cles: list[tuple[str, str]]) -> None:
        """Les états d'un client qui n'est plus évalué (inactif, parti, sorti d'une règle) : il repartira de zéro."""
        t = self._t
        with self._e.begin() as c:
            for regle, client in cles:
                c.execute(delete(t).where(t.c.regle == regle, t.c.client == client))

    def oublier(self, regles_gardees: set[str]) -> None:
        """Les états des règles retirées s'effacent."""
        with self._e.begin() as c:
            c.execute(delete(self._t).where(self._t.c.regle.not_in(regles_gardees) if regles_gardees else True))
