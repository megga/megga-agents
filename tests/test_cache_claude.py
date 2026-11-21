"""Le cache d'Anthropic (21.11.2026) : chaque requête à Claude porte le marqueur automatique et la marque des outils, sans
réseau (un faux serveur relève le corps envoyé)."""

import asyncio
import json

import httpx2 as httpx
from agno.agent import Agent

from noyau.agent import modele

REPONSE = {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5", "stop_reason": "end_turn",
           "content": [{"type": "text", "text": "Bonjour."}],
           "usage": {"input_tokens": 10, "output_tokens": 2, "cache_read_input_tokens": 8, "cache_creation_input_tokens": 0}}


def meteo(ville: str) -> str:
    """La météo d'une ville."""
    return "beau"


def test_claude_marque_le_cache():
    envoyes = []

    def repondre(r: httpx.Request):
        envoyes.append(json.loads(r.content))
        return httpx.Response(200, json=REPONSE)

    m = modele("claude-sonnet-5-5", {"ANTHROPIC_API_KEY": "cle-d-essai"}, reflexion=True, effort="medium", cache=True)
    m.http_client = httpx.AsyncClient(transport=httpx.MockTransport(repondre))
    sortie = asyncio.run(Agent(model=m, tools=[meteo], instructions=["Réponds."], telemetry=False).arun("Bonjour"))
    corps = envoyes[0]
    assert corps["cache_control"] == {"type": "ephemeral", "ttl": "1h"}  # le marqueur automatique, sur la fin de la requête
    assert corps["tools"][-1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}  # les outils, stables d'un tour à l'autre
    assert all(m["cache_control"]["ttl"] == "1h" for m in [corps, corps["tools"][-1]])  # une seule durée, sinon refus
    assert corps["thinking"] == {"type": "adaptive"} and corps["output_config"] == {"effort": "medium"}  # rien d'autre ne change
    assert sortie.metrics.cache_read_tokens == 8  # lu par Agno, donc par le relevé


def test_seul_l_agent_principal_marque_le_cache():
    from noyau.agent import construire
    from test_lot3 import conf

    assert construire(conf(), None, {"ANTHROPIC_API_KEY": "cle-d-essai"}).model.request_params == {"cache_control": {"type": "ephemeral", "ttl": "1h"}}
    # Un appel unique (l'oral, le fil, le juge) : aucune marque, il ne relirait jamais le cache.
    seul = modele("claude-haiku-5-5", {"ANTHROPIC_API_KEY": "cle-d-essai"})
    assert not seul.request_params and not seul.cache_tools


def test_deepseek_sans_marque():
    assert "cache_control" not in (getattr(modele("deepseek-v4-pro", {}), "request_params", None) or {})


def test_les_consignes_ne_bougent_plus_d_un_tour_a_l_autre(tmp_path):
    """L'heure et le Contexte partent à la fin du message du tour, après le texte de la personne, marqué pour le cache ;
    l'historique n'en garde que le texte. Au tour suivant, tout jusqu'au texte d'avant est identique : il se relit."""
    from agno.db.sqlite import SqliteDb

    from noyau.agent import construire
    from test_lot3 import conf

    envoyes = []

    def repondre(r: httpx.Request):
        envoyes.append(json.loads(r.content))
        return httpx.Response(200, json=REPONSE)

    vus = []

    async def contexte(personne):
        vus.append(personne)
        return f"Demande en cours n° {len(vus)}"

    m = modele("claude-sonnet-5-5", {"ANTHROPIC_API_KEY": "cle-d-essai"}, cache=True)
    m.http_client = httpx.AsyncClient(transport=httpx.MockTransport(repondre))
    agent = construire(conf(), SqliteDb(db_file=str(tmp_path / "agent.db")), {}, principal=m, contexte=contexte)

    async def deux_tours():
        await agent.arun("Bonjour", user_id="41790000000", session_id="s")
        await agent.arun("Et demain ?", user_id="41790000000", session_id="s")

    asyncio.run(deux_tours())
    premier, second = envoyes
    assert premier["system"] == second["system"]  # ni l'heure ni le Contexte
    assert premier["system"][-1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert "current time" not in json.dumps(premier["system"]) and "Demande en cours" not in json.dumps(premier["system"])
    # Le message du tour : le texte de la personne, marqué, puis le Contexte.
    texte, ajout = premier["messages"][-1]["content"]
    assert texte == {"type": "text", "text": "Bonjour", "cache_control": {"type": "ephemeral", "ttl": "1h"}}
    assert "The current time is" in ajout["text"] and "Demande en cours n° 1" in ajout["text"]
    # Au tour suivant, l'historique rend le texte seul : le début de la requête est celui que le cache a marqué.
    assert second["messages"][0]["content"] == [{"type": "text", "text": "Bonjour"}]
    texte, ajout = second["messages"][-1]["content"]
    assert texte["text"] == "Et demain ?" and "Demande en cours n° 2" in ajout["text"] and "n° 1" not in json.dumps(second)
    assert vus == ["41790000000", "41790000000"]
    # Quatre marques au plus, la limite d'Anthropic : les outils, les consignes, le texte du tour, la fin.
    assert json.dumps(second).count("cache_control") <= 4


def test_marquer_le_tour_ne_touche_qu_au_dernier_message_du_tour():
    from noyau.agent import CONTEXTE_DU_TOUR, marquer_le_tour

    sans = [{"role": "user", "content": [{"type": "text", "text": "Bonjour"}]}]
    assert marquer_le_tour(json.loads(json.dumps(sans))) == sans  # pas de Contexte (l'oral, le juge) : rien ne change
    avec = [{"role": "user", "content": [{"type": "text", "text": "Salut" + CONTEXTE_DU_TOUR + "x"}]},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "t", "name": "f", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}]}]
    sortie = marquer_le_tour(avec)
    assert sortie[0]["content"][0] == {"type": "text", "text": "Salut", "cache_control": {"type": "ephemeral", "ttl": "1h"}}
    assert sortie[2]["content"] == [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}]  # un résultat d'outil, intact
