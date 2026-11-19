"""Une simulation d'échange entre agents, sans réseau ni clé : MEGGA Estates avec une collègue, Léa.

Les modèles sont des acteurs de théâtre (ils disent des phrases écrites d'avance) ; tout le reste est le vrai moteur :
les vrais agents Agno, le vrai catalogue de démonstration, le vrai relais, la vraie base (SQLite jetable).

    .venv/bin/python scripts/simulation_collegues.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agno.models.base import Model  # noqa: E402
from agno.models.response import ModelResponse  # noqa: E402

from noyau import config as configuration, stockage  # noqa: E402
from noyau.agent import construire  # noqa: E402
from noyau.app import outils_du_client, relais_des_collegues  # noqa: E402
from noyau.config import PRINCIPAL  # noqa: E402


@dataclass
class Acteur(Model):
    """Un modèle qui joue un rôle : `jouer(messages, n)` rend un texte, ou un appel d'outil (nom, arguments)."""

    id: str = "acteur"
    name: str = "Acteur"
    provider: str = "simulation"
    jouer: object = None
    vus: list = field(default_factory=list)

    def _repondre(self, messages):
        self.vus.append(messages)
        suite = self.jouer(messages)
        if isinstance(suite, tuple):
            nom, arguments = suite
            return ModelResponse(role="assistant", tool_calls=[{"id": f"appel{len(self.vus)}", "type": "function",
                                                                "function": {"name": nom, "arguments": json.dumps(arguments)}}])
        return ModelResponse(role="assistant", content=suite)

    def invoke(self, messages=None, **kw):
        return self._repondre(messages or [])

    async def ainvoke(self, messages=None, **kw):
        return self._repondre(messages or [])

    def invoke_stream(self, *a, **kw):
        yield self.invoke(*a, **kw)

    async def ainvoke_stream(self, *a, **kw):
        yield await self.ainvoke(*a, **kw)

    def _parse_provider_response(self, response, **kw):
        return response

    def _parse_provider_response_delta(self, response):
        return response


def dernier(messages, role):
    return next((m for m in reversed(messages) if getattr(m, "role", None) == role), None)


def alix(messages):
    """Alix : pose la question à Léa, puis répond avec ce que Léa lui a dit."""
    retour = dernier(messages, "tool")
    if retour is None:
        return ("demander_a_un_collegue", {"collegue": "lea", "question": "Quelles villas à Genève dépassent 5 millions, et que sait-on de la plus chère ?"})
    return "Bonjour Greg ! D'après Léa : " + str(retour.content).split(": ", 1)[-1]


def lea(messages):
    """Léa : cherche dans le catalogue, puis répond à sa collègue."""
    retour = dernier(messages, "tool")
    if retour is None:
        return ("chercher_biens", {"mots": "villa"})
    return "Voici ce que dit le catalogue de démonstration : " + " ".join(str(retour.content).split())[:260]


def main() -> None:
    base = configuration.lire("clients/megga-estates.yaml").model_dump(mode="json")
    base["roles"] = {"gestionnaire": {"outils": ["rappels", "immobilier", "collegues"]}}
    base["collegues"] = {"lea": {"prenom": "Léa", "metier": "Elle connaît les biens du catalogue et leurs prix.", "outils": ["immobilier"]}}
    conf = configuration.Config.model_validate(base)
    url = f"sqlite:///{tempfile.mkdtemp()}/simulation.db"
    db = stockage.base_agno(url)
    cles = {"ANTHROPIC_API_KEY": "simulation"}
    relais = relais_des_collegues(conf, db, cles, url, modele_des_collegues=Acteur(jouer=lea))
    role = conf.les_roles()["gestionnaire"]
    agent = construire(conf, db, cles, principal=Acteur(jouer=alix), role=role, nom_role="gestionnaire",
                       outils=outils_du_client(conf, stockage.Rappels(url), role.outils, relais=relais))

    question = "Greg : Alix, peux-tu me dire quelles villas dépassent 5 millions à Genève ?"
    print(question)
    sortie = asyncio.run(agent.arun(question, user_id="+41790000001", session_id="simulation"))
    print(f"\nAlix à Greg : {sortie.content}\n")
    print("Ce que le moteur a rangé (megga_echanges) :")
    for ligne in stockage.Echanges(url).depuis(0):
        print(f"  #{ligne['ordre']} {ligne['de']} -> {ligne['a']} [{ligne['etat']}, relais {ligne['profondeur']}] {ligne['texte'][:110]}")
    print("\nCe que le suivi en dit :")
    from noyau.suivi import resumer

    r = resumer(conf, stockage.Suivi(url).tours(0), {}, 0, 0)
    print(f"  tours de personnes : {r['tours']}, personnes : {r['personnes']}, réponses de collègues : {r['echanges']['reponses']}")
    print(f"  collègues : {list(r['echanges']['collegues'])}")


if __name__ == "__main__":
    main()
