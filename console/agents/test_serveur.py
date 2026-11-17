"""Le serveur d'agents de l'essai local : inscription, jeton, réponse AG-UI au fil de l'eau."""

import importlib
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTS_DONNEES", str(tmp_path))
    monkeypatch.setenv("AGENTS_JETON", "secret-essai")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import serveur

    importlib.reload(serveur)
    return TestClient(serveur.app)


ENTETE = {"Authorization": "Bearer secret-essai"}


def entree(texte):
    return {"threadId": "fil-1", "runId": "tour-1", "state": {}, "messages": [{"id": "m1", "role": "user", "content": texte}],
            "tools": [], "context": [], "forwardedProps": {}}


def test_jeton_exige(client):
    assert client.put("/agents/agent-abc", json={"prenom": "Lou", "metier": "garage", "entreprise": "Garage du Lac"}).status_code == 401
    assert client.post("/agents/agent-abc/agui", json=entree("Bonjour"), headers={"Authorization": "Bearer faux"}).status_code == 401


def test_metier_inconnu_refuse(client):
    r = client.put("/agents/agent-abc", json={"prenom": "Lou", "metier": "boulangerie", "entreprise": "X"}, headers=ENTETE)
    assert r.status_code == 400


def test_agent_inconnu(client):
    assert client.post("/agents/inconnu-1/agui", json=entree("Bonjour"), headers=ENTETE).status_code == 404


@pytest.mark.parametrize("metier", ["generaliste", "immobilier", "sante", "hotellerie", "juridique", "commerce", "fiduciaire", "garage"])
def test_chaque_metier_repond_au_fil_de_l_eau(client, metier):
    r = client.put(f"/agents/agent-{metier}", json={"prenom": "Lou", "metier": metier, "entreprise": "Essai SA"}, headers=ENTETE)
    assert r.status_code == 200 and r.json()["en_service"] is True
    with client.stream("POST", f"/agents/agent-{metier}/agui", json=entree("Avez-vous de la place jeudi ?"), headers=ENTETE) as flux:
        assert flux.headers["content-type"].startswith("text/event-stream")
        evenements = [json.loads(l[5:]) for l in flux.iter_lines() if l.startswith("data:")]
    types = [e["type"] for e in evenements]
    assert types[0] == "RUN_STARTED" and types[-1] == "RUN_FINISHED"
    texte = "".join(e.get("delta", "") for e in evenements if e["type"] == "TEXT_MESSAGE_CONTENT")
    assert "Avez-vous de la place jeudi ?" in texte
