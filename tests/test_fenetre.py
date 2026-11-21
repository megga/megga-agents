"""La fenêtre de l'historique avance par paquets (21.11.2026) : au-delà de `tours`, le début de ce que l'agent relit ne
bouge qu'une fois tous les PAS_FENETRE tours, pour que le cache d'Anthropic relise l'historique au lieu de le réécrire."""

import asyncio
import json

import httpx2 as httpx
from agno.db.sqlite import SqliteDb

from noyau.agent import PAS_FENETRE, construire, fenetre, modele
from test_lot3 import conf

REPONSE = {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5", "stop_reason": "end_turn",
           "content": [{"type": "text", "text": "Oui."}], "usage": {"input_tokens": 10, "output_tokens": 2}}


def test_la_fenetre_n_avance_que_par_paquets():
    assert PAS_FENETRE == 6
    vues = [fenetre(n, 12) for n in range(40)]
    assert vues[:13] == [12] * 13  # rien ne glisse tant que la conversation est courte
    assert all(12 <= v <= 17 for v in vues)  # jamais moins qu'avant, au plus cinq tours de plus
    debuts = [n - v for n, v in enumerate(vues) if n >= 12]
    # Le début de ce qui est relu ne change qu'une fois tous les six tours.
    assert sum(1 for a, b in zip(debuts, debuts[1:]) if a != b) == len(debuts) // PAS_FENETRE


def _agent(tmp_path, envoyes):
    def repondre(r: httpx.Request):
        envoyes.append(json.loads(r.content))
        return httpx.Response(200, json=REPONSE)

    m = modele("claude-sonnet-5-5", {"ANTHROPIC_API_KEY": "cle-d-essai"}, cache=True)
    m.http_client = httpx.AsyncClient(transport=httpx.MockTransport(repondre))
    base = conf()
    c = base.model_copy(update={"historique": base.historique.model_copy(update={"tours": 2})})
    return construire(c, SqliteDb(db_file=str(tmp_path / "agent.db")), {}, principal=m)


def test_l_agent_relit_par_paquets_et_le_debut_reste_stable(tmp_path):
    envoyes = []
    agent = _agent(tmp_path, envoyes)

    async def tours():
        for i in range(16):
            await agent.arun(f"Message {i}", user_id="41790000000", session_id="s")

    asyncio.run(tours())
    textes = [[m["content"][0]["text"] for m in e["messages"] if m["role"] == "user"] for e in envoyes]
    relus = [len(t) - 1 for t in textes]  # le message du tour n'est pas de l'historique
    assert relus == [min(n, fenetre(n, 2)) for n in range(16)]
    premiers = [t[0] for t in textes]
    # Le premier message relu ne change que quand le paquet avance : au 8e tour, puis au 14e.
    assert premiers == ["Message 0"] * 8 + ["Message 6"] * 6 + ["Message 12"] * 2


def test_deux_personnes_en_meme_temps_gardent_chacune_leur_fenetre(tmp_path):
    envoyes = []
    agent = _agent(tmp_path, envoyes)

    async def ensemble():
        for i in range(9):  # une longue conversation d'abord
            await agent.arun(f"Long {i}", user_id="41790000001", session_id="longue")
        envoyes.clear()
        await asyncio.gather(agent.arun("Court", user_id="41790000002", session_id="courte"),
                             agent.arun("Long 9", user_id="41790000001", session_id="longue"))

    asyncio.run(ensemble())
    par_texte = {e["messages"][-1]["content"][0]["text"]: e for e in envoyes}
    assert len(par_texte["Court"]["messages"]) == 1  # rien à relire
    assert sum(1 for m in par_texte["Long 9"]["messages"] if m["role"] == "user") - 1 == fenetre(9, 2)
