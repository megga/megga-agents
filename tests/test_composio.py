"""Les connecteurs de Composio : les outils choisis par MEGGA, leur exécution, les liens de connexion de l'atelier."""

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from atelier.app import creer
from noyau import composio
from noyau.agent import consignes
from noyau.app import outils_du_client
from noyau.config import Config, manques
from test_lot5 import ADMIN, MEGGA, FaussePorte, FauxModele, jeton_client, nouveau_client

BASE = {"id": "agence-lac", "nom_agent": "Lea", "entreprise": "Agence du Lac", "zone": "europe"}
OUTILS = ("GMAIL_SEND_EMAIL", "GOOGLECALENDAR_FIND_FREE_SLOTS")
SCHEMA = {"type": "object", "properties": {"to": {"type": "string"}, "body": {"type": "string"}}, "required": ["to"]}


class FauxComposio:
    """Le service de Composio : la liste des outils, leur exécution, les liens et les comptes, appels gardés."""

    def __init__(self, echec: bool = False):
        self.appels, self.echec = [], echec

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        corps = json.loads(requete.content) if requete.content else None
        self.appels.append((requete.method, requete.url.path, dict(requete.url.params), corps, requete.headers.get("x-api-key")))
        if self.echec:
            return httpx.Response(500, text="panne")
        chemin = requete.url.path.removeprefix("/api/v3.1")
        if chemin == "/tools":
            slugs = requete.url.params["tool_slugs"].split(",")
            return httpx.Response(200, json={"items": [{"slug": s, "name": s.title(), "description": f"Outil {s}",
                                                        "input_parameters": SCHEMA, "version": "20260101_00"}
                                                       for s in slugs if s != "INCONNU_OUTIL"]})
        if chemin.startswith("/tools/execute/"):
            if corps["arguments"].get("to") == "refus@exemple.ch":
                return httpx.Response(200, json={"successful": False, "error": "adresse refusée", "data": {}})
            return httpx.Response(200, json={"successful": True, "data": {"id": "m1", "envoye": True}})
        if chemin == "/connected_accounts/link":
            return httpx.Response(201, json={"redirect_url": "https://connect.composio.dev/l/abc", "expires_at": "2026-11-22T10:00:00Z",
                                             "connected_account_id": "ca_1", "link_token": "t"})
        if chemin == "/connected_accounts":
            return httpx.Response(200, json={"items": [{"id": "ca_1", "status": "ACTIVE", "created_at": "2026-11-21",
                                                        "toolkit": {"slug": "gmail"}, "data": {"access_token": "secret"}}]})
        return httpx.Response(404, text="inconnu")


def connecteurs(faux, outils=OUTILS):
    return composio.Composio("cle-composio", "agence-lac", composio.ReglageComposio(outils=outils), transport=httpx.MockTransport(faux))


def test_les_connecteurs_se_reglent_pour_tout_metier_et_chaque_role():
    for metier in ("general", "immobilier"):
        conf = Config.model_validate({**BASE, "metier": metier, "outils": ["connecteurs"], "composio": {"outils": list(OUTILS)}})
        assert conf.composio.outils == OUTILS and manques(conf) == []
    conf = Config.model_validate({**BASE, "roles": {"gestionnaire": {"outils": ["rappels", "connecteurs"]}, "visiteur": {}},
                                  "composio": {"outils": ["GMAIL_SEND_EMAIL"]}})
    assert manques(conf) == []
    sans = Config.model_validate({**BASE, "outils": ["connecteurs"]})
    assert manques(sans) == ["les connecteurs attendent leurs outils Composio (réglage de MEGGA)"]
    for faux in (["gmail_send"], ["GMAIL_SEND_EMAIL", "GMAIL_SEND_EMAIL"], []):
        with pytest.raises(ValueError):
            Config.model_validate({**BASE, "composio": {"outils": faux}})


def test_seuls_les_outils_choisis_arrivent_et_s_executent():
    faux = FauxComposio()
    outils = connecteurs(faux, ("GMAIL_SEND_EMAIL", "INCONNU_OUTIL")).outils()
    assert [o.name for o in outils] == ["gmail_send_email"]   # l'outil introuvable est laissé de côté
    assert outils[0].parameters == SCHEMA and outils[0].description == "Outil GMAIL_SEND_EMAIL"
    methode, chemin, params, _, cle = faux.appels[0]
    assert (methode, chemin, params["tool_slugs"], cle) == ("GET", "/api/v3.1/tools", "GMAIL_SEND_EMAIL,INCONNU_OUTIL", "cle-composio")
    rendu = asyncio.run(outils[0].entrypoint(to="anne@exemple.ch", body="Bonjour"))
    assert json.loads(rendu) == {"id": "m1", "envoye": True}
    _, chemin, _, corps, _ = faux.appels[-1]
    assert chemin == "/api/v3.1/tools/execute/GMAIL_SEND_EMAIL"
    assert corps == {"user_id": "agence-lac", "arguments": {"to": "anne@exemple.ch", "body": "Bonjour"}, "version": "20260101_00"}
    refus = asyncio.run(outils[0].entrypoint(to="refus@exemple.ch"))
    assert refus.startswith("Échec de l'outil : adresse refusée") and "ne dis pas le contraire" in refus


def test_composio_en_panne_ne_bloque_pas_l_agent():
    assert connecteurs(FauxComposio(echec=True)).outils() == []
    c = connecteurs(FauxComposio())
    c.outils()
    c.transport = httpx.MockTransport(FauxComposio(echec=True))
    assert "injoignable" in asyncio.run(c.executer("GMAIL_SEND_EMAIL", None, {"to": "a@b.ch"}))


def test_le_groupe_connecteurs_donne_les_outils_et_la_consigne():
    conf = Config.model_validate({**BASE, "outils": ["connecteurs"], "composio": {"outils": list(OUTILS)}})
    noms = [getattr(o, "name", None) for o in outils_du_client(conf, None, groupes=("connecteurs",), connecteurs=connecteurs(FauxComposio()))]
    assert noms == ["gmail_send_email", "googlecalendar_find_free_slots"]
    assert outils_du_client(conf, None, groupes=(), connecteurs=connecteurs(FauxComposio())) == []
    assert composio.CONSIGNES in consignes(conf)
    assert composio.CONSIGNES not in consignes(Config.model_validate(BASE))


@pytest.fixture
def atelier(tmp_path):
    faux = FauxComposio()
    t = TestClient(creer({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/a.db", "ESSAIS_DIR": str(tmp_path / "essais"),
                          "COMPOSIO_API_KEY": "cle-composio"}, porte=FaussePorte(), principal_essai=FauxModele(),
                         transport_composio=httpx.MockTransport(faux)))
    t.faux = faux
    return t


def test_megga_cree_le_lien_et_le_client_voit_ses_comptes(atelier):
    t = atelier
    nouveau_client(t)
    r = t.post("/atelier/clients/exemple/composio/lien", headers=MEGGA, json={"auth_config": "ac_gmail01", "retour": "https://megga.ai/ok"})
    assert r.status_code == 201, r.text
    assert r.json() == {"client": "exemple", "lien": "https://connect.composio.dev/l/abc", "expire": "2026-11-22T10:00:00Z", "compte": "ca_1"}
    assert t.faux.appels[-1][3] == {"auth_config_id": "ac_gmail01", "user_id": "exemple", "callback_url": "https://megga.ai/ok"}
    client = jeton_client(t)
    assert t.post("/atelier/clients/exemple/composio/lien", headers=client, json={"auth_config": "ac_gmail01"}).status_code == 403
    r = t.get("/atelier/clients/exemple/composio/comptes", headers=client)
    assert r.json() == {"client": "exemple", "comptes": [{"id": "ca_1", "boite": "gmail", "etat": "ACTIVE", "cree": "2026-11-21"}]}
    assert "secret" not in r.text   # aucun jeton du compte ne sort de l'atelier
    assert t.get("/atelier/clients/voisin/composio/comptes", headers=client).status_code == 404
    for corps in ({"auth_config": "gmail"}, {"auth_config": "ac_gmail01", "retour": "http://x.ch"}):
        assert t.post("/atelier/clients/exemple/composio/lien", headers=MEGGA, json=corps).status_code == 400


def test_sans_cle_composio_les_routes_le_disent(tmp_path):
    t = TestClient(creer({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/a.db", "ESSAIS_DIR": str(tmp_path / "essais")},
                         porte=FaussePorte(), principal_essai=FauxModele()))
    nouveau_client(t)
    r = t.get("/atelier/clients/exemple/composio/comptes", headers=MEGGA)
    assert r.status_code == 503 and "COMPOSIO_API_KEY" in r.json()["erreur"]


def test_agno_appelle_l_outil_comme_pendant_un_tour():
    from agno.tools.function import FunctionCall

    outil = connecteurs(FauxComposio()).outils()[0]
    assert outil.to_dict() == {"name": "gmail_send_email", "description": "Outil GMAIL_SEND_EMAIL", "parameters": SCHEMA}
    r = asyncio.run(FunctionCall(function=outil, arguments={"to": "anne@exemple.ch"}).aexecute())
    assert r.status == "success" and json.loads(r.result) == {"id": "m1", "envoye": True}
