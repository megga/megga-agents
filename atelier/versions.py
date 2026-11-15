"""L'historique des configurations, sur les composants d'Agno (agno.db, Agno 3.2).

Un client = un composant « agent » ; chaque configuration = une version.
  brouillon (draft)    modifiable par l'essai seulement (compteur d'essais)
  publiée (published)  immuable ; la version courante est celle en service
Publier une version la rend courante ; revenir en arrière, c'est rendre courante
une version déjà publiée (set_current_version). Les numéros ne sont jamais réutilisés.

On s'appuie sur la couche de base d'Agno, pas sur ses routes HTTP /components :
celles-ci écrivent des agents Agno sans connaître notre configuration, et leurs
droits suivent l'utilisateur du jeton, pas nos rôles client et MEGGA.
"""

from __future__ import annotations

import json
from typing import Any

from agno.db.base import BaseDb, ComponentType

from noyau.config import Config


def _notes(brut: Any) -> dict:
    try:
        n = json.loads(brut or "{}")
        return n if isinstance(n, dict) else {}
    except ValueError:
        return {}


def _version(v: dict, avec_config: bool = True) -> dict:
    n = _notes(v.get("notes"))
    sortie = {
        "version": v["version"],
        "etat": "publiee" if v.get("stage") == "published" else "brouillon",
        "auteur": n.get("auteur"),
        "base": n.get("base"),
        "essais": n.get("essais", 0),
        "cree_le": v.get("created_at"),
    }
    if avec_config:
        sortie["config"] = v.get("config")
    return sortie


class Versions:
    def __init__(self, db: BaseDb):
        self.db = db

    # Les clients

    def clients(self) -> list[dict]:
        tous, page = [], 0
        while True:
            lot, total = self.db.list_components(component_type=ComponentType.AGENT, limit=100, offset=page * 100)
            tous += lot
            page += 1
            if len(tous) >= total or not lot:
                return tous

    def client(self, ident: str) -> dict | None:
        return self.db.get_component(ident, component_type=ComponentType.AGENT)

    def reglages(self, ident: str) -> dict:
        return dict((self.client(ident) or {}).get("metadata") or {})

    def regler(self, ident: str, **valeurs) -> dict:
        """Les réglages de l'atelier sur ce client (reprise en main), fusionnés."""
        meta = {**self.reglages(ident), **valeurs}
        self.db.upsert_component(ident, metadata=meta)
        return meta

    def creer(self, conf: Config, auteur: str) -> dict:
        _, v = self.db.create_component_with_config(
            component_id=conf.id,
            component_type=ComponentType.AGENT,
            name=conf.nom_agent,
            description=conf.entreprise,
            config=conf.model_dump(mode="json"),
            metadata={"gere_par_megga": False},
            stage="draft",
            notes=json.dumps({"auteur": auteur, "base": None, "essais": 0}),
        )
        return _version(v)

    # Les versions

    def ajouter(self, conf: Config, auteur: str, base: int | None) -> dict:
        v = self.db.upsert_config(
            conf.id,
            config=conf.model_dump(mode="json"),
            stage="draft",
            notes=json.dumps({"auteur": auteur, "base": base, "essais": 0}),
        )
        return _version(v)

    def version(self, ident: str, numero: int) -> dict | None:
        v = self.db.get_config(ident, version=numero)
        return _version(v) if v else None

    def derniere(self, ident: str) -> dict | None:
        v = self.db.get_latest_config(ident)
        return _version(v) if v else None

    def dernieres(self, idents: set[str]) -> dict[str, int | None]:
        """Le numéro de la dernière version de chaque client, en une lecture."""
        return {i: (v or {}).get("version") for i, v in self.db.get_latest_configs(idents).items()}

    def historique(self, ident: str) -> list[dict]:
        return [_version(v, avec_config=False) for v in self.db.list_configs(ident)]

    def courante(self, ident: str) -> int | None:
        return (self.client(ident) or {}).get("current_version")

    def en_service(self, ident: str) -> dict | None:
        """La version en service et sa configuration, ou None."""
        n = self.courante(ident)
        return self.version(ident, n) if n else None

    def noter_essai(self, ident: str, numero: int) -> None:
        """Compte un essai sur un brouillon (une version publiée a déjà servi)."""
        v = self.db.get_config(ident, version=numero)
        if v and v.get("stage") != "published":
            n = _notes(v.get("notes"))
            n["essais"] = int(n.get("essais", 0)) + 1
            self.db.upsert_config(ident, version=numero, notes=json.dumps(n))

    def mettre_en_service(self, ident: str, numero: int, avant: int | None) -> None:
        """Publie un brouillon (il devient courant) ou rend courante une version publiée.

        `avant` : la version qu'on croit en service (garde d'Agno : refus si elle a changé).
        """
        reglages = self.reglages(ident)
        v = self.db.get_config(ident, version=numero)
        if v is None:
            raise ValueError("version introuvable")
        garde = avant or 0  # 0 : aucune version en service
        if v.get("stage") == "published":
            if not self.db.set_current_version(ident, version=numero, expected_current_version=garde):
                raise ValueError("version non publiée")
        else:
            self.db.upsert_config(ident, version=numero, stage="published", expected_current_version=garde)
        # La ligne du composant suit la version en service : prénom, entreprise, et nos réglages,
        # que la publication d'Agno réécrit.
        conf = v.get("config") or {}
        self.db.upsert_component(ident, name=conf.get("nom_agent"), description=conf.get("entreprise"), metadata=reglages)
