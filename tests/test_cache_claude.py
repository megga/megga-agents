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

    m = modele("claude-sonnet-5-5", {"ANTHROPIC_API_KEY": "cle-d-essai"}, reflexion=True, effort="medium")
    m.http_client = httpx.AsyncClient(transport=httpx.MockTransport(repondre))
    sortie = asyncio.run(Agent(model=m, tools=[meteo], instructions=["Réponds."], telemetry=False).arun("Bonjour"))
    corps = envoyes[0]
    assert corps["cache_control"] == {"type": "ephemeral"}  # le marqueur automatique, sur la fin de la requête
    assert corps["tools"][-1]["cache_control"] == {"type": "ephemeral"}  # les outils, stables d'un tour à l'autre
    assert corps["thinking"] == {"type": "adaptive"} and corps["output_config"] == {"effort": "medium"}  # rien d'autre ne change
    assert sortie.metrics.cache_read_tokens == 8  # lu par Agno, donc par le relevé


def test_deepseek_sans_marque():
    assert "cache_control" not in (getattr(modele("deepseek-v4-pro", {}), "request_params", None) or {})
