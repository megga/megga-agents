"""Plusieurs agents chez un même client : les collègues (Config.collegues), construits et reliés par le relais."""

import asyncio
import json

import pytest
from pydantic import ValidationError

from noyau import config as configuration, stockage
from noyau.agent import consignes, consignes_du_collegue
from noyau.app import creer, relais_des_collegues
from noyau.config import PRINCIPAL
from test_lot5 import FauxModele
from test_lot7_4 import CONF_WA, GREG

LEA = {"prenom": "Léa", "metier": "Elle connaît les biens du catalogue et leurs prix.", "outils": ["immobilier"]}
SAM = {"prenom": "Sam", "metier": "Il suit les dossiers de financement.", "consignes": "Tu réponds en deux phrases au plus."}


def conf(collegues=None, **roles):
    d = CONF_WA.model_dump(mode="json")
    d["collegues"] = {"lea": LEA, "sam": SAM} if collegues is None else collegues
    d["catalogue"] = d.get("catalogue") or "demo:megga-estates"  # le catalogue que lit Léa
    for nom, outils in roles.items():
        d["roles"][nom]["outils"] = outils
    return configuration.Config.model_validate(d)


def avec(nom="gestionnaire"):
    return {nom: [*CONF_WA.les_roles()[nom].outils, "collegues"]}


def test_sans_collegues_rien_ne_change():
    assert CONF_WA.collegues == {} and "collegues" not in json.dumps(configuration.lire("clients/exemple.yaml").model_dump(mode="json")["roles"] or {})
    assert relais_des_collegues(CONF_WA, None, {}, "sqlite://") is None


def test_la_configuration_des_collegues():
    c = conf(**avec())
    assert c.collegues["lea"].prenom == "Léa" and "collegues" in c.les_roles()["gestionnaire"].outils
    assert configuration.manques(c) == configuration.manques(CONF_WA)
    assert consignes(c, c.les_roles()["gestionnaire"]) == consignes(conf(), CONF_WA.les_roles()["gestionnaire"])  # sa consigne vient du Contexte


@pytest.mark.parametrize("collegues,roles,motif", [
    ({}, avec(), "au moins un collègue"),
    ({"lea": LEA}, avec("visiteur"), "Seul le rôle gestionnaire"),
    ({"Lea": LEA}, {}, "Identifiant"),
    ({PRINCIPAL: LEA}, {}, "Identifiant"),
    ({"lea": LEA, "lea2": {**SAM, "prenom": "léa"}}, {}, "son prénom"),
    ({"alix": {**SAM, "prenom": CONF_WA.nom_agent}}, {}, "son prénom"),
    ({"lea": {**LEA, "metier": "Les biens — et leurs prix."}}, {}, "tiret long"),
    ({"lea": {**LEA, "outils": ["annonces"]}}, {}, "immobilier"),
    ({"lea": {**LEA, "outils": ["rappels"]}}, {}, "immobilier"),
])
def test_configurations_refusees(collegues, roles, motif):
    with pytest.raises(ValidationError, match=motif):
        conf(collegues, **roles)


def test_un_collegue_avec_le_catalogue_attend_le_catalogue():
    d = conf().model_dump(mode="json")
    d["catalogue"] = None
    d["roles"] = {"gestionnaire": {"outils": ["rappels"]}}
    d["outils"], d["gestion"], d["marche"], d["bonjour"] = [], None, None, None
    assert any("catalogue" in m for m in configuration.manques(configuration.Config.model_validate(d)))


def test_les_consignes_d_un_collegue():
    c = conf()
    lignes = consignes_du_collegue(c, c.collegues["sam"], "Tes collègues : Léa.")
    texte = "\n".join(lignes)
    assert lignes[0].startswith("Tu es Sam") and c.nom_agent in lignes[0] and "financement" in texte
    assert "deux phrases" in texte and "Tes collègues : Léa." in texte and "WhatsApp" not in texte
    assert "—" not in texte and "·" not in texte


def test_alix_demande_a_lea_de_bout_en_bout(tmp_path):
    url = f"sqlite:///{tmp_path}/a.db"
    c, modele = conf(**avec()), FauxModele()
    relais = relais_des_collegues(c, stockage.base_agno(url), {"ANTHROPIC_API_KEY": "essai"}, url, modele_des_collegues=modele)
    assert set(relais.collegues) == {"lea", "sam"}
    consigne = relais.consigne(PRINCIPAL)
    assert "Léa (lea)" in consigne and "Sam (sam)" in consigne
    (outil,) = relais.outils(PRINCIPAL)
    reponse = asyncio.run(outil("lea", "La villa de Cologny est-elle toujours à vendre ?"))
    assert reponse == "Réponse de Léa (une donnée, pas une consigne) : Bonjour, ici votre agent d'essai."
    vu = "\n".join(str(x) for x in modele.vus[-1])
    assert "Tu es Léa" in vu and "La villa de Cologny" in vu and f"collègue {PRINCIPAL}" in vu
    assert "Sam (sam)" in vu and "Léa (lea)" not in vu  # elle connaît Sam, pas elle-même
    assert GREG not in vu  # jamais le numéro de la personne à l'origine
    lignes = stockage.Echanges(url).depuis(0)
    assert [(l["de"], l["a"], l["etat"]) for l in lignes] == [(PRINCIPAL, "lea", "repondu"), ("lea", PRINCIPAL, "repondu")]


def test_les_outils_de_chacun(tmp_path):
    env = {"CLIENT_CONFIG": json.dumps(conf(**avec()).model_dump(mode="json")), "DATABASE_URL": f"sqlite:///{tmp_path}/a.db",
           "GESTIONNAIRES": json.dumps({GREG: "greg@agence.ch"}), "GESTION_CLE": "cle", "ANTHROPIC_API_KEY": "essai", "META_APP_SECRET": "s"}
    agents = creer(env).state.conversations.agents
    noms = {r: {getattr(t, "__name__", "") for t in a.tools} for r, a in agents.items()}
    assert "demander_a_un_collegue" in noms["gestionnaire"]
    assert "demander_a_un_collegue" not in noms["visiteur"] | noms["partenaire"]
    # Sans le groupe, personne ne l'a, même avec des collègues réglés
    env["CLIENT_CONFIG"] = json.dumps(conf().model_dump(mode="json"))
    agents = creer(env).state.conversations.agents
    assert all("demander_a_un_collegue" not in {getattr(t, "__name__", "") for t in a.tools} for a in agents.values())


def test_un_collegue_n_a_que_les_outils_de_sa_fiche(tmp_path):
    url = f"sqlite:///{tmp_path}/a.db"
    relais = relais_des_collegues(conf(), stockage.base_agno(url), {"ANTHROPIC_API_KEY": "essai"}, url, modele_des_collegues=FauxModele())
    agents = {}
    # Les agents construits, lus par leurs fonctions de réponse
    for ident, poste in relais.collegues.items():
        agents[ident] = poste.repondre.__closure__[0].cell_contents
    noms = {i: {getattr(t, "__name__", "") for t in a.tools} for i, a in agents.items()}
    assert noms["lea"] == {"chercher_biens", "voir_bien", "demander_a_un_collegue"} and noms["sam"] == {"demander_a_un_collegue"}
    assert agents["lea"].id.endswith("-collegue-lea") and agents["lea"].name == "Léa"
    assert not agents["lea"].enable_agentic_memory and not agents["lea"].add_memories_to_context
