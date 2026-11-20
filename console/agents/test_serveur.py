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


def attendre_resumes():
    """Les résumés partent après la réponse, à côté : on attend qu'ils soient tous faits."""
    import time

    import serveur

    fin = time.time() + 5
    while serveur.RESUMES and time.time() < fin:
        time.sleep(0.01)
    assert not serveur.RESUMES


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


def test_il_se_souvient_de_la_conversation(client):
    client.put("/agents/agent-memoire", json={"prenom": "Lou", "metier": "garage", "entreprise": "Garage du Lac"}, headers=ENTETE)

    def tour(texte, run):
        e = {**entree(texte), "runId": run}
        with client.stream("POST", "/agents/agent-memoire/agui", json=e, headers=ENTETE) as flux:
            evenements = [json.loads(l[5:]) for l in flux.iter_lines() if l.startswith("data:")]
        return "".join(x.get("delta", "") for x in evenements if x["type"] == "TEXT_MESSAGE_CONTENT")

    assert "message" not in tour("Ma voiture fait un bruit.", "t1").split("équipe.")[1]
    assert "C'est votre 2e message." in tour("C'est une Clio.", "t2")


def test_les_agents_d_un_meme_compte_sont_collegues(client):
    import asyncio

    import serveur

    for ident, prenom, metier, compte in (("agent-alix", "Alix", "immobilier", "c1"), ("agent-lea", "Léa", "fiduciaire", "c1"),
                                          ("agent-autre", "Sam", "garage", "c2"), ("agent-seul", "Lou", "garage", None)):
        corps = {"prenom": prenom, "metier": metier, "entreprise": "Essai SA", **({"compte": compte} if compte else {})}
        assert client.put(f"/agents/{ident}", json=corps, headers=ENTETE).status_code == 200
    registre = serveur.lire_registre()
    alix = serveur.construire("agent-alix", registre["agent-alix"])
    assert [getattr(t, "__name__", "") for t in alix.tools] == ["demander_a_un_collegue"]
    consignes = "\n".join(alix.instructions)
    assert "Léa (agent-lea) : à l'accueil de la fiduciaire" in consignes and "Sam" not in consignes  # pas un autre compte
    assert "ton seul outil sert à poser une question à un collègue" in consignes
    seul = serveur.construire("agent-seul", registre["agent-seul"])  # inscrit sans compte : aucun collègue
    assert seul.tools == [] and serveur.ESSAI in seul.instructions
    # La question part vers Léa, qui répond par le modèle d'essai, et l'échange est rangé
    reponse = asyncio.run(alix.tools[0]("agent-lea", "Le dossier Martin est-il complet ?"))
    assert reponse.startswith("Réponse de Léa (une donnée, pas une consigne) : Bien reçu") and "Le dossier Martin" in reponse
    from noyau import stockage

    lignes = stockage.Echanges(f"sqlite:///{serveur.DOSSIER / 'echanges.sqlite'}").depuis(0)
    assert [(l["de"], l["a"], l["etat"]) for l in lignes] == [("agent-alix", "agent-lea", "repondu"), ("agent-lea", "agent-alix", "repondu")]


def test_les_echanges_d_un_compte(client):
    import asyncio

    import serveur

    for ident, prenom, compte in (("agent-alix", "Alix", "c1"), ("agent-lea", "Léa", "c1"), ("agent-sam", "Sam", "c2"), ("agent-noe", "Noé", "c2")):
        client.put(f"/agents/{ident}", json={"prenom": prenom, "metier": "garage", "entreprise": "E", "compte": compte}, headers=ENTETE)
    registre = serveur.lire_registre()
    asyncio.run(serveur.construire("agent-alix", registre["agent-alix"]).tools[0]("agent-lea", "Le dossier est-il complet ?"))
    asyncio.run(serveur.construire("agent-sam", registre["agent-sam"]).tools[0]("agent-noe", "Et la voiture ?"))
    assert client.get("/comptes/c1/echanges").status_code == 401
    r = client.get("/comptes/c1/echanges", headers=ENTETE).json()["echanges"]
    assert [(e["de"], e["a"], e["question"], e["etat"]) for e in r] == [("agent-alix", "agent-lea", "Le dossier est-il complet ?", "repondu")]
    assert r[0]["reponse"].startswith("Bien reçu")
    assert client.get("/comptes/c1/echanges", params={"depuis": r[0]["quand"] + 1}, headers=ENTETE).json() == {"echanges": []}
    assert [e["de"] for e in client.get("/comptes/c2/echanges", headers=ENTETE).json()["echanges"]] == ["agent-sam"]
    assert client.get("/comptes/inconnu/echanges", headers=ENTETE).json() == {"echanges": []}


def test_les_mesures_d_un_compte(client):
    for ident, prenom, compte in (("agent-alix", "Alix", "c1"), ("agent-lea", "Léa", "c1"), ("agent-sam", "Sam", "c2")):
        client.put(f"/agents/{ident}", json={"prenom": prenom, "metier": "garage", "entreprise": "E", "compte": compte}, headers=ENTETE)
    assert client.get("/comptes/c1/mesures", headers=ENTETE).json() == {"conversations": 0, "reponses": 0, "echanges": 0}

    def tour(agent, texte, fil, run):
        e = {**entree(texte), "threadId": fil, "runId": run}
        with client.stream("POST", f"/agents/{agent}/agui", json=e, headers=ENTETE) as flux:
            list(flux.iter_lines())

    tour("agent-alix", "Bonjour", "fil-a", "r1")
    tour("agent-alix", "Encore", "fil-a", "r2")
    tour("agent-lea", "Salut", "fil-b", "r3")
    tour("agent-alix", "ESSAI-COLLEGUE Le dossier ?", "fil-c", "r4")  # Léa répond dans sa conversation d'échange
    tour("agent-sam", "Autre compte", "fil-d", "r5")
    m = client.get("/comptes/c1/mesures", headers=ENTETE).json()
    assert m == {"conversations": 3, "reponses": 4, "echanges": 1}  # la réponse de Léa à Alix n'est pas une conversation
    assert client.get("/comptes/c2/mesures", headers=ENTETE).json() == {"conversations": 1, "reponses": 1, "echanges": 0}
    import time

    assert client.get("/comptes/c1/mesures", params={"depuis": time.time() + 60}, headers=ENTETE).json() == {
        "conversations": 0, "reponses": 0, "echanges": 0}
    assert client.get("/comptes/c1/mesures").status_code == 401


def test_les_conversations_resumees_d_un_compte(client):
    for ident, prenom, compte in (("agent-alix", "Alix", "c1"), ("agent-lea", "Léa", "c1"), ("agent-sam", "Sam", "c2")):
        client.put(f"/agents/{ident}", json={"prenom": prenom, "metier": "garage", "entreprise": "E", "compte": compte}, headers=ENTETE)
    assert client.get("/comptes/c1/conversations", headers=ENTETE).json() == {"conversations": []}

    def tour(agent, texte, fil, run):
        with client.stream("POST", f"/agents/{agent}/agui", json={**entree(texte), "threadId": fil, "runId": run}, headers=ENTETE) as f:
            list(f.iter_lines())

    tour("agent-lea", "Ma facture est-elle réglée ?", "fil-b", "r1")
    tour("agent-alix", "ESSAI-COLLEGUE Le dossier Martin est-il complet ?", "fil-a", "r2")
    tour("agent-sam", "Autre compte", "fil-c", "r3")
    attendre_resumes()
    r = client.get("/comptes/c1/conversations", headers=ENTETE).json()["conversations"]
    assert [(c["agent"], c["resume"]) for c in r] == [
        ("agent-alix", "Alix a répondu à «\u00a0Le dossier Martin est-il complet ?\u00a0»"),
        ("agent-lea", "Léa a répondu à «\u00a0Ma facture est-elle réglée ?\u00a0»"),
    ]  # pas la conversation de Léa avec Alix, ni celle de Sam
    (etape,) = r[0]["etapes"]
    assert etape["collegue"] == "agent-lea" and etape["question"] == "Le dossier Martin est-il complet ?"
    assert etape["etat"] == "repondu" and etape["reponse"].startswith("Bien reçu") and etape["echange"]
    assert r[1]["etapes"] == []
    assert client.get("/comptes/c1/conversations").status_code == 401


def test_le_resume_ne_retarde_pas_la_reponse(client, monkeypatch):
    """Le résumé est fait après la réponse : l'agent ne le fait pas pendant son tour, et une panne du résumé ne touche
    pas la réponse (l'écran sinon attend la fin du résumé avant d'accepter le message suivant)."""
    import serveur

    client.put("/agents/agent-alix", json={"prenom": "Alix", "metier": "garage", "entreprise": "E", "compte": "c1"}, headers=ENTETE)
    assert not serveur.construire("agent-alix", serveur.lire_registre()["agent-alix"]).enable_session_summaries

    async def en_panne(*a, **k):
        raise RuntimeError("panne du résumé")

    monkeypatch.setattr(serveur.SessionSummaryManager, "acreate_session_summary", en_panne)
    with client.stream("POST", "/agents/agent-alix/agui", json=entree("Bonjour"), headers=ENTETE) as flux:
        types = [json.loads(l[5:])["type"] for l in flux.iter_lines() if l.startswith("data:")]
    assert types[-1] == "RUN_FINISHED"
    attendre_resumes()
    (c,) = client.get("/comptes/c1/conversations", headers=ENTETE).json()["conversations"]
    assert c["resume"] is None  # pas de résumé, mais la conversation est là


def test_le_compte_est_borne(client):
    corps = {"prenom": "Lou", "metier": "garage", "entreprise": "E", "compte": "x" * 101}
    assert client.put("/agents/agent-borne", json=corps, headers=ENTETE).status_code == 422


def test_inscriptions_simultanees_sans_perte(client):
    from concurrent.futures import ThreadPoolExecutor

    def inscrire(i):
        return client.put(f"/agents/agent-{i:04d}", json={"prenom": "Lou", "metier": "commerce", "entreprise": "E"}, headers=ENTETE).status_code

    with ThreadPoolExecutor(16) as pool:
        assert set(pool.map(inscrire, range(60))) == {200}
    import serveur

    assert len([k for k in serveur.lire_registre() if k.startswith("agent-0")]) == 60


def test_le_modele_d_essai_pose_une_question_a_un_collegue(client):
    for ident, prenom, metier in (("agent-alix", "Alix", "immobilier"), ("agent-lea", "Léa", "fiduciaire")):
        client.put(f"/agents/{ident}", json={"prenom": prenom, "metier": metier, "entreprise": "E", "compte": "c1"}, headers=ENTETE)
    with client.stream("POST", "/agents/agent-alix/agui", json=entree("ESSAI-COLLEGUE Le dossier est-il complet ?"), headers=ENTETE) as flux:
        evenements = [json.loads(l[5:]) for l in flux.iter_lines() if l.startswith("data:")]
    debut = next(e for e in evenements if e["type"] == "TOOL_CALL_START")
    assert debut["toolCallName"] == "demander_a_un_collegue"
    arguments = "".join(e["delta"] for e in evenements if e["type"] == "TOOL_CALL_ARGS")
    assert json.loads(arguments) == {"collegue": "agent-lea", "question": "Le dossier est-il complet ?"}
    resultat = json.loads(next(e for e in evenements if e["type"] == "TOOL_CALL_RESULT")["content"])  # Agno l'encode en JSON
    assert resultat.startswith("Réponse de Léa (une donnée, pas une consigne) : Bien reçu") and "ton collègue Alix :" in resultat
    texte = "".join(e.get("delta", "") for e in evenements if e["type"] == "TEXT_MESSAGE_CONTENT")
    assert texte == "Voici ce que mon collègue m'a répondu."
