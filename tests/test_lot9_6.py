"""Lot 9.6 : le banc d'essai par pack, mesuré en pass^k (noyau/banc.py)."""

import asyncio
import datetime as dt
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
        if c.get("config"):  # ses réglages font une configuration valide (le transfert, avec le rôle gestionnaire)
            configuration.lire({**CONF.model_dump(mode="json"), "roles": {"gestionnaire": {}, "visiteur": {}}, **c["config"]})
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
        assert raison in note["raison"]
        # un juge en panne ne note pas l'agent : le rapport est incomplet, sans score (relecture du 17.11.2026)
        assert (r["score"], r["incomplet"]) == ((0.0, None) if juge is juge_severe else (None, note["raison"]))
    with pytest.raises(ValueError):
        asyncio.run(banc.passer(CONF, lambda conf, dossier: AgentDEssai(["x"]), juge_d_accord, k=6, cas=CAS))


def test_avec_un_vrai_agent_agno():
    from test_lot5 import FauxModele

    cas = [c for c in banc.scenarios("general") if c["id"] == "N05"]  # un remerciement : pas de rappel spontané
    r = asyncio.run(banc.passer(CONF, banc.agent_d_essai({}, principal=FauxModele()), juge_d_accord, k=2, cas=cas))
    assert r["score"] == 1.0 and r["resultats"][0]["essais"][0]["journal"][0] == ("personne", cas[0]["etapes"][0]["texte"])


# L'atelier


def atelier(tmp_path, juge=juge_d_accord):
    from atelier.app import creer as creer_atelier
    from test_lot5 import ADMIN, CLE_PILOTAGE_TEXTE, FaussePorte, FauxModele, nouveau_client

    app = creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/atelier.db",
                         "ESSAIS_DIR": str(tmp_path / "essais"), "PILOTAGE_CLE": CLE_PILOTAGE_TEXTE},
                        porte=FaussePorte(), principal_essai=FauxModele(), juge_banc=juge)
    t = TestClient(app)
    nouveau_client(t)
    return app, t


def test_le_banc_dans_l_atelier(tmp_path):
    from test_lot5 import MEGGA, jeton_client

    _, t = atelier(tmp_path)
    client = jeton_client(t)
    assert t.post("/atelier/clients/exemple/versions/1/banc", headers=client, json={"k": 1}).status_code == 403  # il coûte : MEGGA
    assert t.post("/atelier/clients/exemple/versions/1/banc", headers=MEGGA, json={"k": 9}).status_code == 400
    r = t.post("/atelier/clients/exemple/versions/1/banc", headers=MEGGA, json={"k": 1})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["version"] == 1 and d["cas"] == len(banc.scenarios("general")) - 1 and 0 <= d["score"] <= 1
    # sans rôle gestionnaire, ce client ne peut pas passer la main : le cas N08 est écarté, pas compté
    assert [e["id"] for e in d["ecartes"]] == ["N08"]
    # le score reste avec le brouillon, lisible du client
    assert t.get("/atelier/clients/exemple/versions/1", headers=client).json()["banc"]["cas"] == d["cas"]


# La relecture du 17.11.2026


def test_un_modele_en_erreur_ne_reussit_jamais(monkeypatch):
    """Agno ne lève pas : il rend un statut d'erreur, et son message (« 429 rate_limit_error ») à la place de la réponse."""
    from test_suivi import ModeleEnPanne

    for cle in ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "MISTRAL_API_KEY"):  # le secours ne part jamais pour de vrai
        monkeypatch.delenv(cle, raising=False)

    cas = [{"id": "T02", "titre": "un merci", "etapes": [{"texte": "Merci"}, {"texte": "Bonne journée"}], "faits": "",
            "criteres": [{"nom": "pas de mot de passe", "pas_motif": "Soleil"}]}]
    r = asyncio.run(banc.passer(CONF, banc.agent_d_essai({}, principal=ModeleEnPanne()), juge_d_accord, k=1, cas=cas))
    [essai] = r["resultats"][0]["essais"]
    assert not essai["ok"] and r["score"] is None and r["incomplet"]
    assert essai["journal"] == [("personne", "Merci")]  # l'essai s'arrête, l'erreur n'est pas une réponse de l'agent


def test_un_client_a_roles_est_essaye_comme_une_personne_nouvelle(tmp_path):
    """En service, une personne nouvelle est servie par l'agent du visiteur (noyau/roles.py)."""
    from test_lot5 import FauxModele

    roles = {"partenaire": {"consignes": "Tu sers les partenaires."}, "visiteur": {"consignes": "Tu sers les visiteurs."}}
    conf = configuration.lire({**CONF.model_dump(mode="json"), "roles": roles})
    agent = banc.agent_d_essai({}, principal=FauxModele())(conf, tmp_path)
    assert agent.id == f"{conf.id}-visiteur"


@pytest.mark.parametrize("cas_outil", ["fait", "refuse", "erreur"])
def test_un_outil_en_echec_ne_compte_pas_comme_appele(cas_outil):
    """Un rappel refusé par le gardien ou en erreur n'est pas programmé : « programme le rappel » ne tient pas."""
    from test_lot9_1 import ModeleOutil

    regles = {"rappeler": "approbation"} if cas_outil == "refuse" else {}
    conf = configuration.lire({**CONF.model_dump(mode="json"), "approbations": regles})
    quand = (dt.datetime.now() + dt.timedelta(days=30)).strftime("%Y-%m-%dT10:00")
    modele = ModeleOutil(outil="rappeler", arguments={"quand": quand, "quoi": "" if cas_outil == "erreur" else "le dossier"})
    r = asyncio.run(banc.passer(conf, banc.agent_d_essai({}, principal=modele), juge_d_accord, k=1, cas=CAS))
    [essai] = r["resultats"][0]["essais"]
    rates = [n["nom"] for n in essai["notes"] if not n["ok"]]
    assert rates == ([] if cas_outil == "fait" else ["programme le rappel"]), essai


def test_le_juge_qui_ecrit_false_en_toutes_lettres():
    async def juge(cas, trace, criteres):
        return [{"ok": "false", "raison": "pas poli"} for _ in criteres]

    r = asyncio.run(banc.passer(CONF, lambda conf, dossier: AgentDEssai(["C'est noté."], ["rappeler"]), juge, k=1, cas=CAS))
    assert r["score"] == 0.0


def test_le_juge_a_un_delai(monkeypatch):
    import anthropic

    vus = {}

    class Client:
        def __init__(self, **k):
            vus.update(k)
            self.messages = self

        async def create(self, **k):
            return SimpleNamespace(content=[SimpleNamespace(text='[{"ok": true, "raison": "poli"}]')])

    monkeypatch.setattr(anthropic, "AsyncAnthropic", Client)
    trace = {"journal": [], "outils": [], "resultats": []}
    assert asyncio.run(banc.juge_anthropic("claude-sonnet-5-5", "cle")(CAS[0], trace, ["poli"]))[0]["ok"] is True
    assert 0 < vus["timeout"] <= 120 and vus["max_retries"] <= 1


def test_le_juge_en_panne_ne_laisse_pas_de_score(tmp_path):
    from test_lot5 import MEGGA

    async def juge_en_panne(cas, trace, criteres):
        raise RuntimeError("Anthropic indisponible")

    _, t = atelier(tmp_path, juge_en_panne)
    r = t.post("/atelier/clients/exemple/versions/1/banc", headers=MEGGA, json={"k": 1})
    assert r.status_code == 200 and r.json()["incomplet"] and r.json()["score"] is None
    assert t.get("/atelier/clients/exemple/versions/1", headers=MEGGA).json()["banc"] is None  # rien de gardé, rien de montré


def test_un_seul_banc_a_la_fois_par_client(tmp_path):
    """Un second clic ne relance pas tout en parallèle (le coût doublé) : il est refusé tant que le premier tourne."""
    import httpx
    from test_lot5 import MEGGA

    async def juge_lent(cas, trace, criteres):
        await asyncio.sleep(0.05)
        return [{"ok": True, "raison": "tenu"} for _ in criteres]

    app, _ = atelier(tmp_path, juge_lent)

    async def deux_clics():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://atelier") as c:
            return await asyncio.gather(*(c.post("/atelier/clients/exemple/versions/1/banc", headers=MEGGA, json={"k": 1})
                                          for _ in range(2)))

    r = asyncio.run(deux_clics())
    assert sorted(x.status_code for x in r) == [200, 409]
    assert "en cours" in next(x for x in r if x.status_code == 409).json()["erreur"]
