"""Lot 9.6 : le banc d'essai par pack, mesuré en pass^k (noyau/banc.py)."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from noyau import banc, config as configuration

CONF = configuration.lire("clients/exemple.yaml")


async def juge_d_accord(cas, trace, criteres):
    return [{"ok": True, "raison": "tenu"} for _ in criteres]


class AgentDEssai:
    """Un agent qui répond `textes[i % len]` à son i-ème message, en appelant `outils`."""

    def __init__(self, textes, outils=()):
        self.textes, self.outils, self.n = textes, outils, 0

    async def arun(self, texte, user_id=None, session_id=None):
        r = self.textes[self.n % len(self.textes)]
        self.n += 1
        return SimpleNamespace(content=r, tools=[SimpleNamespace(tool_name=o, tool_args={}, result="ok") for o in self.outils])


CAS = [{"id": "T01", "titre": "un rappel", "etapes": [{"texte": "Rappelle-moi demain"}], "faits": "",
        "criteres": [{"nom": "programme le rappel", "outil": ["rappeler"]}, {"nom": "pas de mot de passe", "pas_motif": "Soleil"},
                     {"nom": "poli", "juge": True}]}]


# Les scénarios


@pytest.mark.parametrize("metier", configuration.NOMS_METIERS)
def test_les_scenarios_sont_bien_formes(metier):
    cas = banc.scenarios(metier)
    assert len({c["id"] for c in cas}) == len(cas) and len(cas) >= 8
    trace = {"journal": [], "reponses": ["x"], "outils": [], "resultats": [], "erreur": None}
    for c in cas:
        assert c["titre"] and c["etapes"] and c["criteres"], c["id"]
        for critere in c["criteres"]:
            if not critere.get("juge"):
                banc.automatique(critere, trace)  # un critère automatique connu, qui ne lève pas
        if c.get("config"):  # ses réglages font une configuration valide
            configuration.lire({**CONF.model_dump(mode="json"), **c["config"]})
        if "documents" in c:  # les documents rangés avant le cas : des titres et des textes
            assert c["documents"] and all(d.get("titre") and d.get("texte") for d in c["documents"]), c["id"]
    assert ("I01" in {c["id"] for c in cas}) == (metier == "immobilier")


def test_les_criteres_automatiques():
    trace = {"reponses": ["Bonjour", "Votre rappel est noté"], "outils": [{"nom": "rappeler", "entree": {}}]}
    assert banc.automatique({"outil": ["rappeler"]}, trace)
    assert not banc.automatique({"pas_outil": ["rappeler"]}, trace)
    assert banc.automatique({"motifs": ["rappel", "bonjour"]}, trace)  # sans tenir compte de la casse
    assert not banc.automatique({"pas_motif": "noté"}, trace)
    assert banc.automatique({"et": [{"outil": ["rappeler"]}, {"pas_motif": "mot de passe"}]}, trace)
    with pytest.raises(ValueError):
        banc.automatique({"inconnu": 1}, trace)


# pass^k


def test_un_agent_regulier_tient_ses_cas_a_chaque_essai():
    r = asyncio.run(banc.passer(CONF, lambda conf, dossier: AgentDEssai(["C'est noté."], ["rappeler"]), juge_d_accord, k=3, cas=CAS))
    assert (r["k"], r["cas"], r["tenus"], r["score"], r["pass_1"]) == (3, 1, 1, 1.0, 1.0)
    assert [e["ok"] for e in r["resultats"][0]["essais"]] == [True, True, True]


def test_un_agent_irregulier_ne_tient_pas_meme_s_il_reussit_une_fois_sur_deux():
    r = asyncio.run(banc.passer(CONF, lambda conf, dossier: AgentDEssai(["C'est noté.", "Soleil brille"], ["rappeler"]), juge_d_accord,
                                k=4, cas=CAS))
    assert (r["score"], r["pass_1"], r["resultats"][0]["reussis"]) == (0.0, 0.5, 2)
    rate = next(e for e in r["resultats"][0]["essais"] if not e["ok"])
    assert [n["nom"] for n in rate["notes"] if not n["ok"]] == ["pas de mot de passe"]


def test_le_juge_qui_refuse_ou_qui_tombe():
    async def juge_severe(cas, trace, criteres):
        return [{"ok": False, "raison": "pas poli"} for _ in criteres]

    async def juge_en_panne(cas, trace, criteres):
        raise RuntimeError("réseau")

    for juge, raison in ((juge_severe, "pas poli"), (juge_en_panne, "juge illisible")):
        r = asyncio.run(banc.passer(CONF, lambda conf, dossier: AgentDEssai(["C'est noté."], ["rappeler"]), juge, k=1, cas=CAS))
        [note] = [n for n in r["resultats"][0]["essais"][0]["notes"] if n.get("juge")]
        assert r["score"] == 0.0 and raison in note["raison"]
    with pytest.raises(ValueError):
        asyncio.run(banc.passer(CONF, lambda conf, dossier: AgentDEssai(["x"]), juge_d_accord, k=6, cas=CAS))


def test_avec_un_vrai_agent_agno():
    from test_lot5 import FauxModele

    cas = [c for c in banc.scenarios("general") if c["id"] == "N05"]  # un remerciement : pas de rappel spontané
    r = asyncio.run(banc.passer(CONF, banc.agent_d_essai({}, principal=FauxModele()), juge_d_accord, k=2, cas=cas))
    assert r["score"] == 1.0 and r["resultats"][0]["essais"][0]["journal"][0] == ("personne", cas[0]["etapes"][0]["texte"])


# L'atelier


def test_le_banc_dans_l_atelier(tmp_path):
    from atelier.app import creer as creer_atelier
    from test_lot5 import ADMIN, CLE_PILOTAGE_TEXTE, MEGGA, FaussePorte, FauxModele, jeton_client, nouveau_client

    t = TestClient(creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/atelier.db",
                                  "ESSAIS_DIR": str(tmp_path / "essais"), "PILOTAGE_CLE": CLE_PILOTAGE_TEXTE},
                                 porte=FaussePorte(), principal_essai=FauxModele(), juge_banc=juge_d_accord))
    nouveau_client(t)
    client = jeton_client(t)
    assert t.post("/atelier/clients/exemple/versions/1/banc", headers=client, json={"k": 1}).status_code == 403  # il coûte : MEGGA
    assert t.post("/atelier/clients/exemple/versions/1/banc", headers=MEGGA, json={"k": 9}).status_code == 400
    r = t.post("/atelier/clients/exemple/versions/1/banc", headers=MEGGA, json={"k": 1})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["version"] == 1 and d["cas"] == len(banc.scenarios("general")) and 0 <= d["score"] <= 1
    # le score reste avec le brouillon, lisible du client
    assert t.get("/atelier/clients/exemple/versions/1", headers=client).json()["banc"]["cas"] == d["cas"]
